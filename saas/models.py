#pylint: disable=too-many-lines

# Copyright (c) 2014, DjaoDjin inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# Implementation Note:
#   The models and managers are declared in the same file to avoid messy
#   import loops.

"""
A billing profile (credit card and deposit bank account) is represented by
an ``Organization``.
An organization (subscriber) subscribes to services provided by another
organization (provider) through a ``Subscription`` to a ``Plan``.

There are no mechanism provided to authenticate as an ``Organization``.
Instead ``User`` authenticate with the application (through a login page
or an API token). They are then able to access URLs related
to an ``Organization`` based on their relation with that ``Organization``.
Two sets or relations are supported: managers and contributors (for details see
:doc:`Security <security>`).
"""

import datetime, logging, re

from dateutil.relativedelta import relativedelta
from django.core.urlresolvers import reverse
from django.core.validators import MaxValueValidator
from django.db import IntegrityError, models, transaction
from django.db.models import Q, Sum
from django.db.models.query import QuerySet
from django.utils.http import quote
from django.utils.decorators import method_decorator
from django.utils.timezone import utc
from django.utils.translation import ugettext_lazy as _
from django_countries.fields import CountryField

from saas import settings
from saas import signals
from saas import get_manager_relation_model, get_contributor_relation_model
from saas.backends import PROCESSOR_BACKEND, ProcessorError
from saas.utils import datetime_or_now, generate_random_slug

from saas.humanize import (as_money, describe_buy_periods,
    DESCRIBE_BALANCE, DESCRIBE_BUY_PERIODS,
    DESCRIBE_CHARGED_CARD, DESCRIBE_CHARGED_CARD_PROCESSOR,
    DESCRIBE_CHARGED_CARD_PROVIDER, DESCRIBE_CHARGED_CARD_REFUND)

LOGGER = logging.getLogger(__name__)

#pylint: disable=old-style-class,no-init


class InsufficientFunds(Exception):

    pass


class OrganizationManager(models.Manager):

    def create_organization(self, name, creation_time):
        creation_time = datetime.datetime.fromtimestamp(creation_time)
        billing_start = creation_time
        if billing_start.day > 28:
            # Insures that the billing cycle will be on the same day
            # every month.
            if billing_start.month >= 12:
                billing_start = datetime.datetime(billing_start.year + 1,
                    1, 1)
            else:
                billing_start = datetime.datetime(billing_start.year,
                    billing_start.month + 1, 1)
        customer = self.create(created_at=creation_time,
            slug=name, billing_start=billing_start)
        return customer

    def accessible_by(self, user):
        """
        Returns a QuerySet of Organziation which *user* either has
        a manager or contributor relation to.

        When *user* is a string instead of a ``User`` instance, it will
        be interpreted as a username.
        """
        if isinstance(user, basestring):
            return self.filter(Q(managers__username=user)
                | Q(contributors__username=user))
        return self.filter(Q(managers__pk=user.pk)
                | Q(contributors__pk=user.pk))


    def find_contributed(self, user):
        """
        Returns a QuerySet of Organziation for which the user is a contributor.
        """
        return self.filter(contributors__id=user.id)

    def find_managed(self, user):
        """
        Returns a QuerySet of Organziation for which *user* is a manager.

        When *user* is a string instead of a ``User`` instance, it will
        be interpreted as a username.
        """
        if isinstance(user, str):
            return self.filter(managers__username=user)
        return self.filter(managers__pk=user.pk)

    def providers(self, subscriptions):
        """
        Set of ``Organization`` which provides the plans referenced
        by *subscriptions*.
        """
        if subscriptions:
            # Would be almost straightforward in a single raw SQL query
            # but expressing it for the Django compiler is not easy.
            selectors = set([])
            for subscription in subscriptions:
                selectors |= set([subscription.plan.organization.id])
            return self.filter(pk__in=selectors)
        return self.none()

    def providers_to(self, organization):
        """
        Set of ``Organization`` which provides active services
        to a subscribed *organization*.
        """
        return self.providers(Subscription.objects.filter(
            organization=organization))


class Organization_Managers(models.Model): #pylint: disable=invalid-name

    organization = models.ForeignKey('Organization')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, db_column='user_id')

    class Meta:
        unique_together = ('organization', 'user')

    def __unicode__(self):
        return '%s-%s' % (unicode(self.organization), unicode(self.user))


class Organization_Contributors(models.Model): #pylint: disable=invalid-name

    organization = models.ForeignKey('Organization')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, db_column='user_id')

    class Meta:
        unique_together = ('organization', 'user')

    def __unicode__(self):
        return '%s-%s' % (unicode(self.organization), unicode(self.user))


class Organization(models.Model):
    """
    The Organization table stores information about who gets
    charged (and who gets paid) for using the service. Users can
    have one of two relationships with an Organization. They can
    either be managers (all permissions) or contributors (use permissions).
    """

    objects = OrganizationManager()
    slug = models.SlugField(unique=True,
        help_text=_("Name of the organization as shown in the url bar."))

    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    is_bulk_buyer = models.BooleanField(default=False,
        help_text=_("Enable this organization to pay subscriptions on behalf"\
" of others."))
    full_name = models.CharField(_('full name'), max_length=60, blank=True)
    # contact by e-mail
    email = models.EmailField(# XXX if we use unique=True here, the project
                              #     wizard must be changed.
        help_text=_("Contact email for support related to the organization."))
    # contact by phone
    phone = models.CharField(max_length=50,
        help_text=_("Contact phone for support related to the organization."))
    # contact by physical mail
    street_address = models.CharField(max_length=150)
    locality = models.CharField(max_length=50)
    region = models.CharField(max_length=50)
    postal_code = models.CharField(max_length=50)
    country = CountryField()

    belongs = models.ForeignKey('Organization',
        related_name='owner', null=True)
    managers = models.ManyToManyField(settings.AUTH_USER_MODEL,
        related_name='manages', through=settings.MANAGER_RELATION)

    contributors = models.ManyToManyField(settings.AUTH_USER_MODEL,
        related_name='contributes', through=settings.CONTRIBUTOR_RELATION)

    # Payment Processing
    # We could support multiple payment processors at the same time by
    # by having a relation to a separate table. For simplicity we only
    # allow on processor per organization at a time.
    subscriptions = models.ManyToManyField('Plan',
        related_name='subscribes', through='Subscription')
    billing_start = models.DateField(null=True, auto_now_add=True)

    funds_balance = models.PositiveIntegerField(default=0,
        help_text="Funds escrowed in cents")
    processor = models.CharField(null=True, max_length=20)
    processor_id = models.CharField(null=True,
        blank=True, max_length=20)
    processor_recipient_id = models.CharField(
        null=True, blank=True, max_length=40,
        help_text=_("Used to deposit funds to the organization bank account"))

    def __unicode__(self):
        return unicode(self.slug)

    @property
    def printable_name(self):
        """
        Insures we can actually print a name visible on paper.
        """
        if self.full_name:
            return self.full_name
        return self.slug

    def add_contributor(self, user, at_time=None):
        """
        Add user as a contributor to organization.
        """
        #pylint: disable=unused-argument
        _, created = \
            get_contributor_relation_model().objects.get_or_create(
            organization=self, user=user)
        return created

    def add_manager(self, user, at_time=None):
        """
        Add user as a manager to organization.
        """
        #pylint: disable=unused-argument
        _, created = get_manager_relation_model().objects.get_or_create(
            organization=self, user=user)
        return created

    def update_bank(self, bank_token):
        PROCESSOR_BACKEND.create_or_update_bank(self, bank_token)
        LOGGER.info('Updated bank information for %s on processor (%s)',
                    self, self.processor_recipient_id)
        signals.bank_updated.send(self)

    def update_card(self, card_token=None):
        PROCESSOR_BACKEND.create_or_update_card(self, card_token)
        LOGGER.info('Updated card information for %s on processor (%s)',
                    self, self.processor_id)
        signals.card_updated.send(self)

    @method_decorator(transaction.atomic)
    def checkout(self, invoicables, user, token=None, remember_card=True):
        """
        *invoiced_items* is a set of ``Transaction`` that will be recorded
        in the ledger. Associated subscriptions will be updated such that
        the ends_at is extended in the future.
        """
        #pylint: disable=too-many-locals
        invoiced_items = []
        new_organizations = []
        for invoicable in invoicables:
            subscription = invoicable['subscription']
            if not subscription.organization.id:
                # When the organization does not exist into the database,
                # we will create a random (i.e. hard to guess) one-time
                # 100% discount coupon that will be emailed to the expected
                # subscriber.
                new_organizations += [subscription.organization]
            else:
                LOGGER.info("[checkout] save subscription of %s to %s",
                    subscription.organization, subscription.plan)
                subscription.save()

            # If the invoicable we are checking out is somehow related to
            # a user shopping cart, we mark that cart item as recorded.
            cart_items = CartItem.objects.filter(
                user=user, plan=subscription.plan, recorded=False)
            if cart_items.exists():
                bulk_items = cart_items.filter(
                    email=subscription.organization.email)
                if bulk_items.exists():
                    cart_item = bulk_items.get()
                else:
                    cart_item = cart_items.get()
                cart_item.recorded = True
                cart_item.save()

            for invoiced_item in invoicable['lines']:
                # We can't set the event_id until the subscription is saved
                # in the database.
                invoiced_item.event_id = subscription.id
                invoiced_item.orig_unit = Transaction.PLAN_UNIT
                invoiced_items += [invoiced_item]

        invoiced_items = Transaction.objects.execute_order(invoiced_items, user)
        charge = Charge.objects.charge_card(self, invoiced_items, user,
            token=token, remember_card=remember_card)

        # Create a 100% discount coupon that will be emailed to
        # the expected subscribers. We do it after the charge is created
        # just that we don't inadvertently email new subscribers in case
        # something goes wrong.
        if new_organizations:
            coupon = Coupon.objects.create(
                code=generate_random_slug(),
                organization=subscription.plan.organization,
                plan=subscription.plan,
                percent=100, nb_attempts=len(new_organizations),
                description='Bulk buying from %s (charge %s)' % (
                    self.printable_name, charge))
            LOGGER.info('Auto-generated Coupon #%s', coupon.id)
            for organization in new_organizations:
                signals.one_time_coupon_generated.send(
                    sender=__name__, subscriber_email=organization.email,
                    coupon=coupon, user=user)

        return charge

    def remove_contributor(self, user):
        """
        Remove user as a contributor to organization.
        """
        relation = get_contributor_relation_model().objects.get(
            organization=self, user=user)
        relation.delete()

    def remove_manager(self, user):
        """
        Add user as a manager to organization.
        """
        relation = get_manager_relation_model().objects.get(
            organization=self, user=user)
        relation.delete()

    def retrieve_bank(self):
        """
        Returns associated bank account as a dictionnary.
        """
        return PROCESSOR_BACKEND.retrieve_bank(self)

    def processor_fee(self, total_amount, processor=None):
        """
        Returns fee amount paid to processor.
        """
        fee_amount = 0
        if processor:
            try:
                provider_subscription = Subscription.objects.get(
                    organization=self, plan__organization=processor)
                fee_amount = provider_subscription.plan.prorate_transaction(
                    total_amount)
            except Subscription.DoesNotExist:
                processor = None
        if not processor:
            fee_amount = PROCESSOR_BACKEND.prorate_transaction(
                total_amount)
        return fee_amount

    @method_decorator(transaction.atomic)
    def withdraw_funds(self, amount, user, created_at=None):
        """
        Withdraw funds from the site into the organization's bank account.

        This will one transactions. For example:

        2014/02/15 elearning withdraws $60 from funds held by djaodjin
            djaodjin:Withdraw                             6000
            elearning:Funds
        """
        created_at = datetime_or_now(created_at)
        descr = "withdraw from %s" % self.printable_name
        if user:
            descr += ' (%s)' % user.username
        # Execute transaction on processor first such that any processor
        # exception will be raised before we attempt to store
        # the ``Transaction``.
        processor_transfer_id, _ = PROCESSOR_BACKEND.create_transfer(
            self, amount, descr)
        Transaction.objects.create(
            event_id=processor_transfer_id,
            descr=descr,
            created_at=created_at,
            dest_unit='usd', # XXX currency on receipient bank account
            dest_amount=amount,
            dest_account=Transaction.WITHDRAW,
            dest_organization=Charge.get_processor(),
            orig_unit='usd', # XXX
            orig_amount=amount,
            orig_account=Transaction.FUNDS,
            orig_organization=self)
        self.funds_balance -= amount
        self.save()


class Agreement(models.Model):

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=150, unique=True)
    modified = models.DateTimeField(auto_now_add=True)

    def __unicode__(self):
        return unicode(self.slug)


class SignatureManager(models.Manager):

    def create_signature(self, agreement, user):
        if isinstance(agreement, basestring):
            agreement = Agreement.objects.get(slug=agreement)
        try:
            sig = self.get(agreement=agreement, user=user)
            sig.last_signed = datetime.datetime.now()
            sig.save()
        except Signature.DoesNotExist:
            sig = self.create(
                agreement=agreement, user=user)
        return sig

    def has_been_accepted(self, agreement, user):
        if isinstance(agreement, basestring):
            agreement = Agreement.objects.get(slug=agreement)
        try:
            sig = self.get(agreement=agreement, user=user)
            if sig.last_signed < agreement.modified:
                return False
        except Signature.DoesNotExist:
            return False
        return True


class Signature(models.Model):

    objects = SignatureManager()

    last_signed = models.DateTimeField(auto_now_add=True)
    agreement = models.ForeignKey(Agreement)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, db_column='user_id',
        related_name='signatures')

    class Meta:
        unique_together = ('agreement', 'user')

    def __unicode__(self):
        return '%s-%s' % (self.user, self.agreement)


class CartItemManager(models.Manager):

    def get_cart(self, user):
        # Order by plan then id so the order is consistent between
        # billing/cart(-.*)/ pages.
        return self.filter(user=user, recorded=False).order_by('plan', 'id')


class CartItem(models.Model):
    """
    A user (authenticated or anonymous) shops for plans by adding them
    to her cart. When placing an order, the user is presented with the billing
    account (``Organization``) those items apply to.

    Historical Note: The billing account was previously required at the time
    the item is added to the cart. The ``cart_items`` is the only extra state
    kept in the session, and kept solely for anonymous users. We do not store
    the billing account in the session. It is retrieved from the url. As a
    result the billing account (i.e. an ``Organization``) is set when an
    order is placed, not when the item is added to the cart.
    """
    objects = CartItemManager()

    created_at = models.DateTimeField(auto_now_add=True,
        help_text=_("date/time at which the item was added to the cart."))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, db_column='user_id',
        related_name='cart_items',
        help_text=_("user who added the item to the cart."))
    plan = models.ForeignKey('Plan', null=True,
        help_text=_("item added to the cart."))
    coupon = models.ForeignKey('Coupon', null=True,
        help_text=_("coupon to apply to the plan."))
    recorded = models.BooleanField(default=False,
        help_text=_("whever the item has been checked out or not."))

    # The following fields are for number of periods pre-paid in advance.
    nb_periods = models.PositiveIntegerField(default=0)

    # The following fields are used for plans priced per seat. They do not
    # refer to a User nor Organization key because those might not yet exist
    # at the time the seat is created.
    first_name = models.CharField(_('first name'), max_length=30, blank=True)
    last_name = models.CharField(_('last name'), max_length=30, blank=True)
    email = models.EmailField(_('email address'), blank=True)

    class Meta:
        unique_together = ('user', 'plan', 'email')

    def __unicode__(self):
        return '%s-%s' % (self.user, self.plan)

    @property
    def descr(self):
        result = '%s from %s' % (
            self.plan.get_title(), self.plan.organization.printable_name)
        if self.email:
            full_name = ' '.join([self.first_name, self.last_name]).strip()
            result = 'Subscribe %s (%s) to %s' % (full_name, self.email, result)
        return result

    @property
    def name(self):
        result = 'cart-%s' % self.plan.slug
        if self.email:
            result = '%s-%s' % (result, quote(self.email))
        return result


class ChargeManager(models.Manager):

    def charge_card(self, customer, transactions, descr=None,
                    user=None, token=None, remember_card=True):
        #pylint: disable=too-many-arguments,too-many-locals
        """
        Create a charge on a customer card.
        """
        # Be careful, stripe will not processed charges less than 50 cents.
        amount, unit = sum_dest_amount(transactions)
        if amount == 0:
            return None
        stmt_descr = Transaction.objects.provider(transactions).printable_name
        descr = DESCRIBE_CHARGED_CARD % {
            'charge': '', 'organization': customer.printable_name}
        if user:
            descr += ' (%s)' % user.username
        try:
            if token:
                if remember_card:
                    customer.update_card(card_token=token)
                    (processor_charge_id, created_at,
                     last4, exp_date) = PROCESSOR_BACKEND.create_charge(
                        customer, amount, unit, descr, stmt_descr)
                else:
                    (processor_charge_id, created_at,
                     last4, exp_date) = PROCESSOR_BACKEND.create_charge_on_card(
                        token, amount, unit, descr, stmt_descr)
            else:
                (processor_charge_id, created_at,
                 last4, exp_date) = PROCESSOR_BACKEND.create_charge(
                    customer, amount, unit, descr, stmt_descr)
            # Create record of the charge in our database
            descr = DESCRIBE_CHARGED_CARD % {'charge': processor_charge_id,
                'organization': customer.printable_name}
            if user:
                descr += ' (%s)' % user.username
            charge = self.create(
                processor_id=processor_charge_id, amount=amount,
                created_at=created_at, description=descr,
                customer=customer, last4=last4, exp_date=exp_date)
            for invoiced in transactions:
                ChargeItem.objects.create(invoiced=invoiced, charge=charge)
            LOGGER.info('Created charge #%s of %d cents to %s',
                        charge.processor_id, charge.amount, customer)
        except ProcessorError:
            LOGGER.error('InvalidRequestError for charge of %d cents to %s',
                        amount, customer)
            raise
        return charge


class Charge(models.Model):
    """
    Keep track of charges that have been emitted by the app.
    We save the last4 and expiration date so we are able to present
    a receipt.
    """
    CREATED = 0
    DONE = 1
    FAILED = 2
    DISPUTED = 3
    CHARGE_STATES = {
        (CREATED, 'created'),
        (DONE, 'done'),
        (FAILED, 'failed'),
        (DISPUTED, 'disputed')
    }

    objects = ChargeManager()

    created_at = models.DateTimeField(auto_now_add=True)
    amount = models.PositiveIntegerField(default=0, help_text="Amount in cents")
    unit = models.CharField(max_length=3, default='usd')
    customer = models.ForeignKey(Organization,
        help_text='organization charged')
    description = models.TextField(null=True)
    last4 = models.PositiveSmallIntegerField()
    exp_date = models.DateField()
    processor = models.SlugField()
    processor_id = models.SlugField(unique=True, db_index=True)
    state = models.PositiveSmallIntegerField(
        choices=CHARGE_STATES, default=CREATED)

    # XXX unique together paid and invoiced.
    # customer and invoiced_items account payble should match.

    def __unicode__(self):
        return unicode(self.processor_id)

    @staticmethod
    def get_processor():
        return Organization.objects.get(pk=settings.PROCESSOR_ID)

    @property
    def invoiced_total_amount(self):
        """
        Returns the total amount of all invoiced items.
        """
        # XXX changed interface of invoiced_total_amount
        amount, unit = sum_dest_amount(Transaction.objects.by_charge(self))
        return amount, unit

    @property
    def is_disputed(self):
        return self.state == self.DISPUTED

    @property
    def is_failed(self):
        return self.state == self.FAILED

    @property
    def is_paid(self):
        return self.state == self.DONE

    @property
    def is_progress(self):
        return self.state == self.CREATED

    def capture(self):
        # XXX Create transaction
        signals.charge_updated.send(sender=__name__, charge=self, user=None)

    def dispute_created(self):
        self.state = self.DISPUTED
        self.save()
        signals.charge_updated.send(sender=__name__, charge=self, user=None)

    def dispute_updated(self):
        self.state = self.DISPUTED
        self.save()
        signals.charge_updated.send(sender=__name__, charge=self, user=None)

    def dispute_closed(self):
        self.state = self.DONE
        self.save()
        signals.charge_updated.send(sender=__name__, charge=self, user=None)

    def failed(self):
        self.state = self.FAILED
        self.save()
        signals.charge_updated.send(sender=__name__, charge=self, user=None)


    @method_decorator(transaction.atomic)
    def payment_successful(self):
        """
        When a charge through the payment processor is sucessful, a transaction
        is created from client payable to processor assets. The amount of the
        charge is then redistributed to the providers (minus processor fee).
        """
        assert self.state == self.CREATED

        # Example:
        # 2014/01/15 charge on xia card
        #     xia:Expenses                                 15800
        #     djaodjin:Income
        processor = self.get_processor()
        charge_transaction = Transaction.objects.create(
            event_id=self.id,
            descr=self.description,
            created_at=self.created_at,
            dest_amount=self.amount,
            dest_account=Transaction.EXPENSES,
            dest_organization=self.customer,
            orig_amount=self.amount,
            orig_account=Transaction.INCOME,
            orig_organization=processor)
        # Once we have created a transaction for the charge, let's
        # redistribute the money to the rightful owners.
        for charge_item in self.charge_items.all(): #pylint: disable=no-member
            invoiced_item = charge_item.invoiced
            subscription = Subscription.objects.get(pk=invoiced_item.event_id)
            provider = subscription.plan.organization
            total_amount = invoiced_item.dest_amount
            fee_amount = provider.processor_fee(total_amount, processor)
            distribute_amount = invoiced_item.dest_amount - fee_amount
            if fee_amount > 0:
                # Example:
                # 2014/01/15 fee to cowork
                #     djaodjin:Funds                               900
                #     xia:Payable:desk
                charge_item.invoiced_fee = Transaction.objects.create(
                    event_id=subscription.id,
                    descr=DESCRIBE_CHARGED_CARD_PROCESSOR % {
                        'charge': self.processor_id,
                        'subscription': subscription},
                    created_at=self.created_at,
                    dest_amount=fee_amount,
                    dest_account=Transaction.FUNDS,
                    dest_organization=processor,
                    orig_amount=fee_amount,
                    orig_account=Transaction.PAYABLE,
                    orig_organization=self.customer)
                charge_item.save()
                processor.funds_balance += fee_amount
                processor.save()

            # Example:
            # 2014/01/15 distribution due to cowork
            #     cowork:Funds                                  8000
            #     xia:Payable:desk
            Transaction.objects.create(
                event_id=subscription.id,
                descr=DESCRIBE_CHARGED_CARD_PROVIDER % {
                        'charge': self.processor_id,
                        'subscription': subscription},
                created_at=self.created_at,
                dest_amount=distribute_amount,
                dest_account=Transaction.FUNDS,
                dest_organization=provider,
                orig_amount=distribute_amount,
                orig_account=Transaction.PAYABLE,
                orig_organization=self.customer)
            provider.funds_balance += distribute_amount
            provider.save()

        invoiced_amount, _ = self.invoiced_total_amount
        if invoiced_amount > self.amount:
            #pylint: disable=nonstandard-exception
            raise IntegrityError("The total amount of invoiced items for "\
              "charge %s exceed the amount of the charge.", self.processor_id)

        self.state = self.DONE
        self.save()

        signals.charge_updated.send(sender=__name__, charge=self, user=None)
        return charge_transaction

    @property
    def provider(self):
        """
        If all the invoiced items on this charge are related to the same
        provider, returns that ``Organization`` otherwise returns the site
        owner.
        """
        #pylint: disable=no-member
        return Transaction.objects.provider([charge_item.invoiced
                         for charge_item in self.charge_items.all()])

    @method_decorator(transaction.atomic)
    def refund(self, linenum, created_at=None):
        # XXX We donot currently supply a *description* for the refund.
        """
        Partially refund a charge for transaction *linenum*.
        """
        assert self.state == self.DONE
        created_at = datetime_or_now(created_at)
        processor = self.get_processor()
        #pylint: disable=no-member
        charge_item = self.charge_items.all()[linenum]
        invoiced_item = charge_item.invoiced
        customer = invoiced_item.dest_organization
        provider = invoiced_item.orig_organization
        total_amount = invoiced_item.dest_amount

        # Record the refund
        # Example:
        # 2014/03/15 refunding the charge
        #     elearning:Refund                              6900
        #     xia:Refunded
        descr = DESCRIBE_CHARGED_CARD_REFUND % {
            'charge': self.processor_id, 'descr': invoiced_item.descr}
        charge_item.refunded = Transaction.objects.create(
            event_id=self.id,
            descr=descr,
            created_at=created_at,
            dest_unit=self.unit,
            dest_amount=total_amount,
            dest_account=Transaction.REFUND,
            dest_organization=provider,
            orig_unit=self.unit,
            orig_amount=total_amount,
            orig_account=Transaction.REFUNDED,
            orig_organization=customer)
        charge_item.save()

        fee_amount = 0
        if charge_item.invoiced_fee:
            # 2014/03/15 elearning promises to refund $69 to Xia
            #     djaodjin:Refund                                900
            #     djaodjin:Funds
            fee_amount = charge_item.invoiced_fee.orig_amount
            Transaction.objects.create(
                event_id=self.id,
                # The Charge id is already included in the description here.
                descr="Refunded %s" % charge_item.invoiced_fee.descr,
                created_at=created_at,
                dest_unit=self.unit,
                dest_amount=fee_amount,
                dest_account=Transaction.REFUND,
                dest_organization=processor,
                orig_unit=self.unit,
                orig_amount=fee_amount,
                orig_account=Transaction.FUNDS,
                orig_organization=processor)
            processor.funds_balance -= fee_amount
            processor.save()

        distribute_amount = total_amount - fee_amount
        if provider.funds_balance - distribute_amount < 0:
            raise InsufficientFunds(
                '%(provider)s has %(funds_available)s of funds available.'\
' %(funds_required)s are required to refund "%(descr)s"' % {
            'provider': provider,
            'funds_available': as_money(abs(provider.funds_balance), self.unit),
            'funds_required': as_money(abs(distribute_amount), self.unit),
            'descr': invoiced_item.descr})

        # 2014/03/15 cancel payment to elearning
        #     djaodjin:Refund                               6000
        #     elearning:Funds
        Transaction.objects.create(
            event_id=self.id,
            descr=descr,
            created_at=created_at,
            dest_unit=self.unit,
            dest_amount=distribute_amount,
            dest_account=Transaction.REFUND,
            dest_organization=processor,
            orig_unit=self.unit,
            orig_amount=distribute_amount,
            orig_account=Transaction.FUNDS,
            orig_organization=provider)
        provider.funds_balance -= distribute_amount
        provider.save()

        PROCESSOR_BACKEND.refund_charge(self, distribute_amount)
        signals.charge_updated.send(sender=__name__, charge=self, user=None)

    def retrieve(self):
        """
        Retrieve the state of charge from the processor.
        """
        PROCESSOR_BACKEND.retrieve_charge(self)
        return self

class ChargeItem(models.Model):
    """
    Keep track of each item invoiced within a ``Charge``.
    """
    charge = models.ForeignKey(Charge, related_name='charge_items')
    invoiced = models.ForeignKey('Transaction', related_name='invoiced_item',
        help_text="transaction invoiced through this charge")
    invoiced_fee = models.ForeignKey('Transaction', null=True,
        related_name='invoiced_fee_item',
        help_text="fee transaction to process the transaction invoiced"\
" through this charge")
    refunded = models.ForeignKey('Transaction', related_name='refunded_item',
        null=True, help_text="transaction for the refund of the charge item")

    class Meta:
        unique_together = ('charge', 'invoiced')

    def __unicode__(self):
        return '%s-%s' % (unicode(self.charge), unicode(self.invoiced))


class Coupon(models.Model):
    """
    Coupons are used on invoiced to give a rebate to a customer.
    """
    #pylint: disable=super-on-old-class
    created_at = models.DateTimeField(auto_now_add=True)
    code = models.SlugField()
    description = models.TextField(null=True, blank=True)
    percent = models.PositiveSmallIntegerField(default=0,
        validators=[MaxValueValidator(100)],
        help_text="Percentage discounted")
    # restrict use in scope
    organization = models.ForeignKey(Organization)
    plan = models.ForeignKey('saas.Plan', null=True, blank=True)
    # restrict use in time and count.
    ends_at = models.DateTimeField(null=True, blank=True)
    nb_attempts = models.IntegerField(null=True, blank=True,
        help_text="Number of times the coupon can be used")

    class Meta:
        unique_together = ('organization', 'code')

    def __unicode__(self):
        return '%s-%s' % (self.organization, self.code)

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if not self.created_at:
            self.created_at = datetime_or_now()
        if not self.ends_at:
            self.ends_at = self.created_at + datetime.timedelta(days=30)
        super(Coupon, self).save(force_insert=force_insert,
             force_update=force_update, using=using,
             update_fields=update_fields)


class PlanManager(models.Manager):

    def as_buy_periods(self, descr):
        """
        Returns a triplet (plan, ends_at, nb_periods) from a string
        formatted with DESCRIBE_BUY_PERIODS.
        """
        plan = None
        nb_periods = 0
        ends_at = datetime.datetime()
        look = re.match(DESCRIBE_BUY_PERIODS % {
                'plan': r'(?P<plan>\S+)',
                'ends_at': r'(?P<ends_at>\d\d\d\d/\d\d/\d\d)',
                'humanized_periods': r'(?P<nb_periods>\d+).*'}, descr)
        if look:
            try:
                plan = self.get(slug=look.group('plan'))
            except Plan.DoesNotExist:
                plan = None
            ends_at = datetime.datetime.strptime(
                look.group('ends_at'), '%Y/%m/%d').replace(tzinfo=utc)
            nb_periods = int(look.group('nb_periods'))
        return (plan, ends_at, nb_periods)


class Plan(models.Model):
    """
    Recurring billing plan
    """
    objects = PlanManager()

    UNSPECIFIED = 0
    HOURLY = 1
    DAILY = 2
    WEEKLY = 3
    MONTHLY = 4
    QUATERLY = 5
    YEARLY = 7

    INTERVAL_CHOICES = [
        (HOURLY, "HOURLY"),
        (DAILY, "DAILY"),
        (WEEKLY, "WEEKLY"),
        (MONTHLY, "MONTHLY"),
        (QUATERLY, "QUATERLY"),
        (YEARLY, "YEARLY"),
        ]

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=50, null=True)
    description = models.TextField()
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    discontinued_at = models.DateTimeField(null=True, blank=True)
    organization = models.ForeignKey(Organization, related_name='plans')
    unit = models.CharField(max_length=3, default='usd')
    setup_amount = models.PositiveIntegerField(default=0,
        help_text=_('One-time charge amount (in cents).'))
    period_amount = models.PositiveIntegerField(default=0,
        help_text=_('Recurring amount per period (in cents).'))
    transaction_fee = models.PositiveIntegerField(default=0,
        help_text=_('Fee per transaction (in per 10000).'))
    interval = models.PositiveSmallIntegerField(
        choices=INTERVAL_CHOICES, default=YEARLY)
    unlock_event = models.CharField(max_length=128, null=True, blank=True,
        help_text=_('Payment required to access full service'))
    # end game
    length = models.PositiveSmallIntegerField(null=True, blank=True,
        help_text=_('Number of intervals the plan before the plan ends.'))
    # Pb with next : maybe create an other model for it
    next_plan = models.ForeignKey("Plan", null=True)

    class Meta:
        unique_together = ('slug', 'organization')

    def __unicode__(self):
        return unicode(self.slug)

    def end_of_period(self, start_time, nb_periods=1):
        result = start_time
        if self.interval == self.HOURLY:
            result += datetime.timedelta(hours=1 * nb_periods)
        elif self.interval == self.DAILY:
            result += datetime.timedelta(days=1 * nb_periods)
        elif self.interval == self.WEEKLY:
            result += datetime.timedelta(days=7 * nb_periods)
        elif self.interval == self.MONTHLY:
            result += relativedelta(months=1 * nb_periods)
        elif self.interval == self.QUATERLY:
            result += relativedelta(months=3 * nb_periods)
        elif self.interval == self.YEARLY:
            result += relativedelta(years=1 * nb_periods)
        return result

    def get_absolute_url(self):
        return reverse('saas_plan_edit', args=(self.organization, self,))

    def get_title(self):
        """
        Returns a printable human-readable title for the plan.
        """
        if self.title:
            return self.title
        return self.slug

    def humanize_period(self, nb_periods):
        result = None
        if self.interval == self.HOURLY:
            result = '%d hour' % nb_periods
        elif self.interval == self.DAILY:
            result = '%d day' % nb_periods
        elif self.interval == self.WEEKLY:
            result = '%d week' % nb_periods
        elif self.interval == self.MONTHLY:
            result = '%d month' % nb_periods
        elif self.interval == self.QUATERLY:
            result = '%d months' % (3 * nb_periods)
        elif self.interval == self.YEARLY:
            result = '%d year' % nb_periods
        if nb_periods > 1:
            result += 's'
        return result

    def prorate_transaction(self, amount):
        """
        Hosting service paid through a transaction fee.
        """
        return (amount * self.transaction_fee) / 10000

    def prorate_period(self, start_time, end_time):
        """
        Return the pro-rate recurring amount for a period
        [start_time, end_time[.

        If end_time - start_time >= interval period, the value
        returned is undefined.
        """
        if self.interval == 1:
            # Hourly: fractional period is in minutes.
            fraction = (end_time - start_time).seconds / 3600
        elif self.interval == 2:
            # Daily: fractional period is in hours.
            fraction = ((end_time - start_time).seconds
                        / (3600 * 24))
        elif self.interval == 3:
            # Weekly, fractional period is in days.
            fraction = (end_time.date() - start_time.date()).days / 7
        elif self.interval in [4, 5]:
            # Monthly and Quaterly: fractional period is in days.
            # We divide by the maximum number of days in a month to
            # the advantage of a customer.
            fraction = (end_time.date() - start_time.date()).days / 31
        elif self.interval == 7:
            # Yearly: fractional period is in days.
            # We divide by the maximum number of days in a year to
            # the advantage of a customer.
            fraction = (end_time.date() - start_time.date()).days / 366
        # Round down to the advantage of a customer.
        return int(self.period_amount * fraction)


class SubscriptionManager(models.Manager):
    #pylint: disable=super-on-old-class

    def active_for(self, organization, ends_at=None):
        """
        Returns active subscriptions for *organization*
        """
        ends_at = datetime_or_now(ends_at)
        return self.filter(organization=organization, ends_at__gt=ends_at)

    def active_with_provider(self, organization, provider, ends_at=None):
        """
        Returns a list of active subscriptions for organization
        for which provider is the owner of the plan.
        """
        ends_at = datetime_or_now(ends_at)
        return self.filter(organization=organization,
            plan__organization=provider, ends_at__gt=ends_at)

    def create(self, **kwargs):
        if not kwargs.has_key('ends_at'):
            created_at = datetime_or_now(kwargs.get('created_at', None))
            plan = kwargs.get('plan')
            return super(SubscriptionManager, self).create(
                ends_at=plan.end_of_period(created_at), **kwargs)
        return super(SubscriptionManager, self).create(**kwargs)

    def new_instance(self, organization, plan, ends_at=None):
        #pylint: disable=no-self-use
        """
        New ``Subscription`` instance which is explicitely not in the db.
        """
        return Subscription(
            organization=organization, plan=plan, ends_at=ends_at)


class Subscription(models.Model):
    """
    ``Subscription`` represent a service contract (``Plan``) between
    two ``Organization``, a subscriber and a provider, that is paid
    by the subscriber to the provider over the lifetime of the subscription.
    """
    objects = SubscriptionManager()

    created_at = models.DateTimeField(auto_now_add=True)
    ends_at = models.DateTimeField()
    organization = models.ForeignKey('Organization')
    plan = models.ForeignKey('Plan')

    class Meta:
        unique_together = ('organization', 'plan')

    def __unicode__(self):
        return '%s-%s' % (unicode(self.organization), unicode(self.plan))

    @property
    def is_locked(self):
        balance, _ = Transaction.objects.get_subscription_balance(self)
        return balance > 0

    def charge_in_progress(self):
        queryset = Charge.objects.filter(
            customer=self.organization, state=Charge.CREATED)
        if queryset.exists():
            return queryset.first()
        return None

    def unsubscribe_now(self):
        self.ends_at = datetime_or_now()
        self.save()

    def create_order(self, nb_periods, prorated_amount=0,
        created_at=None, descr=None, discount_percent=0):
        #pylint: disable=too-many-arguments
        """
        Each time a customer orders a subscription from a provider,
        a Transaction is recorded that goes from the provider ``Receivable``
        account to the customer ``Payable`` account.

            yyyy/mm/dd description
                   customer:Payable                       amount
                   provider:Receivable

        Note: nb_periods is stored in the Transaction orig_amount.
        """
        if not descr:
            amount = int(
                (prorated_amount + (self.plan.period_amount * nb_periods))
                * (100 - discount_percent) / 100)
            ends_at = self.plan.end_of_period(self.ends_at, nb_periods)
            descr = describe_buy_periods(self.plan, ends_at, nb_periods)
            if discount_percent:
                descr += ' - a %d%% discount' % discount_percent
        else:
            # If we already have a description, all bets are off on
            # what the amount represents (see unlock_event).
            amount = prorated_amount
        created_at = datetime_or_now(created_at)
        return Transaction(
            created_at=created_at,
            descr=descr,
            orig_amount=nb_periods,
            orig_unit=Transaction.PLAN_UNIT,
            orig_account=Transaction.INCOME, # XXX Receivable
            orig_organization=self.plan.organization,
            dest_amount=amount,
            dest_unit=self.plan.unit,
            dest_account=Transaction.PAYABLE,
            dest_organization=self.organization,
            event_id=self.id)


class TransactionManager(models.Manager):

    def by_charge(self, charge):
        #select * from transactions inner join charge_items on
        #transaction.id=charge_items.invoiced and charge_items.charge=charge;
        return self.filter(invoiced_item__charge=charge)

    def by_subsciptions(self, subscriptions, at_time=None):
        """
        Returns a ``QuerySet`` of all transactions related to a set
        of subscriptions.
        """
        queryset = self.filter(
            models.Q(dest_account=Transaction.PAYABLE)
            | models.Q(dest_account=Transaction.REDEEM),
            event_id__in=subscriptions)
        if at_time:
            queryset = queryset.filter(created_at=at_time)
        return queryset.order_by('created_at')

    def create_credit(self, customer, amount):
        credit = self.create(
            orig_organization=get_current_provider(), # XXX move to Organization
            dest_organization=customer,
            orig_account='Incentive', dest_account='Balance',
            amount=amount,
            descr='Credit for creating an organization')
        credit.save()
        return credit

    def execute_order(self, invoiced_items, user=None):
        """
        Save invoiced_items, a set of ``Transaction`` and update when
        each associated ``Subscription`` ends.

        This method returns the invoiced items as a QuerySet.

        Constraints: All invoiced_items to same customer
        """
        invoiced_items_ids = []
        for invoiced_item in invoiced_items:
            if invoiced_item.event_id:
                # XXX When an customer pays on behalf of an organization
                # which does not exist in the database, we cannot create
                # the subscription, hence we do not have an event_id
                # at this point.
                pay_now = True
                subscription = Subscription.objects.get(
                    pk=invoiced_item.event_id)
                if invoiced_item.orig_unit == Transaction.PLAN_UNIT:
                    subscription.ends_at = subscription.plan.end_of_period(
                        subscription.ends_at, invoiced_item.orig_amount)
                subscription.save()
                if (subscription.plan.unlock_event
                    and invoiced_item.dest_amount == 0):
                    # We are dealing with access now, pay later, orders.
                    invoiced_item.dest_amount = subscription.plan.period_amount
                    pay_now = False
                invoiced_item.orig_amount = invoiced_item.dest_amount
                invoiced_item.orig_unit = invoiced_item.dest_unit
                invoiced_item.save()
                if pay_now:
                    invoiced_items_ids += [invoiced_item.id]
        signals.order_executed.send(
            sender=__name__, invoiced_items=invoiced_items_ids, user=user)
        return self.filter(id__in=invoiced_items_ids)

    def get_organization_balance(self, organization, account=None, until=None):
        """
        Returns the balance on an organization's account
        (by default: ``Payable``).
        """
        until = datetime_or_now(until)
        if not account:
            account = Transaction.PAYABLE
        dest_amount, dest_unit = sum_dest_amount(self.filter(
            dest_organization=organization, dest_account=account,
            created_at__lt=until))
        orig_amount, orig_unit = sum_orig_amount(self.filter(
            orig_organization=organization, orig_account=account,
            created_at__lt=until))
        if dest_unit != orig_unit:
            LOGGER.error('orig and dest balances until %s for account'\
' %s of %s have different unit (%s vs. %s).', until, account, organization,
                         orig_unit, dest_unit)
        return dest_amount - orig_amount, dest_unit

    def get_organization_payable(self, organization,
                                 until=None, created_at=None):
        """
        Returns a ``Transaction`` for the organization balance.
        """
        until = datetime_or_now(until)
        if not created_at:
            # Use *until* to avoid being off by a few microseconds.
            created_at = datetime_or_now(until)
        balance, unit = self.get_organization_balance(organization)
        return Transaction(
            created_at=created_at,
            # Re-use Description template here:
            descr=DESCRIBE_BALANCE % {'plan': organization},
            orig_unit=unit,
            orig_amount=balance,
            orig_account=Transaction.PAYABLE,
            orig_organization=organization,
            dest_unit=unit,
            dest_amount=balance,
            dest_account=Transaction.PAYABLE,
            dest_organization=organization)

    def get_subscription_balance(self, subscription):
        """
        Returns the ``Payable`` balance on a subscription.

        The balance on a subscription is used to determine when
        a subscription is locked (balance due) or unlocked (no balance).
        """
        dest_amount, dest_unit = sum_dest_amount(self.filter(
            dest_organization=subscription.organization,
            dest_account=Transaction.PAYABLE,
            event_id=subscription.id))
        orig_amount, orig_unit = sum_orig_amount(self.filter(
            orig_organization=subscription.organization,
            orig_account=Transaction.PAYABLE,
            event_id=subscription.id))
        if dest_unit != orig_unit:
            LOGGER.error('orig and dest balances for subscription '\
' %s have different unit (%s vs. %s).', subscription, orig_unit, dest_unit)
        return dest_amount - orig_amount, dest_unit

    def get_subscription_payable(self, subscription, created_at=None):
        """
        Returns a ``Transaction`` for the subscription balance.
        """
        created_at = datetime_or_now(created_at)
        balance, unit = self.get_subscription_balance(subscription)
        return Transaction(
            created_at=created_at,
            descr=DESCRIBE_BALANCE % {'plan': subscription.plan},
            orig_unit=unit,
            orig_amount=balance,
            orig_account=Transaction.PAYABLE,
            orig_organization=subscription.organization,
            dest_unit=unit,
            dest_amount=balance,
            dest_account=Transaction.PAYABLE,
            dest_organization=subscription.organization)

    def get_subscription_later(self, subscription, created_at=None):
        """
        Returns a ``Transaction`` for the subscription balance to be paid later.
        """
        created_at = datetime_or_now(created_at)
        balance, unit = self.get_subscription_balance(subscription)
        return Transaction(
            created_at=created_at,
            descr=('Pay balance of %s on %s later'
                   % (as_money(balance, unit), subscription.plan)),
            orig_unit=unit,
            orig_amount=balance,
            orig_account=Transaction.PAYABLE,
            orig_organization=subscription.organization,
            dest_unit=unit,
            dest_amount=0,
            dest_account=Transaction.PAYABLE,
            dest_organization=subscription.organization)

    @staticmethod
    def provider(invoiced_items):
        """
        If all subscriptions referenced by *invoiced_items* are to the same
        provider, return it otherwise return the site owner.
        """
        result = None
        for invoiced_item in invoiced_items:
            subscription = Subscription.objects.get(pk=invoiced_item.event_id)
            if not result:
                result = subscription.plan.organization
            elif result != subscription.plan.organization:
                result = get_current_provider()
                break
        if not result:
            result = get_current_provider()
        return result


class Transaction(models.Model):
    '''The Transaction table stores entries in the double-entry bookkeeping
    ledger.

    'Invoiced' comes from the service. We use for acrual tax reporting.
    We have one 'invoiced' for each job? => easy to reconciliate.

    'Balance' is amount due.

    use 'ledger register' for tax acrual tax reporting.
    '''
    PLAN_UNIT = '___'

    # provider side
    BACKLOG = 'Backlog'
    FUNDS = 'Funds'           # <= 0 receipient side
    INCOME = 'Income'         # <= 0 receipient side
    WITHDRAW = 'Withdraw'
    REFUND = 'Refund'       # >= 0 receipient side

    # customer side
    EXPENSES = 'Expenses'   # >= 0 billing side
    PAYABLE = 'Payable'     # >= 0 billing side
    REFUNDED = 'Refunded'   # <= 0 billing side

    CHARGEBACK = 'Chargeback'
    REDEEM = 'Redeem'
    WRITEOFF = 'Writeoff'

    objects = TransactionManager()

    # Implementation Note:
    # An exact created_at is to important to let auto_now_add mess with it.
    created_at = models.DateTimeField()

    orig_account = models.CharField(max_length=30, default="unknown")
    orig_organization = models.ForeignKey(Organization,
        related_name="outgoing")
    orig_amount = models.PositiveIntegerField(default=0,
        help_text=_('amount withdrawn from origin in origin units'))
    orig_unit = models.CharField(max_length=3, default="usd",
        help_text=_('Measure of units on origin account'))

    dest_account = models.CharField(max_length=30, default="unknown")
    dest_organization = models.ForeignKey(Organization,
        related_name="incoming")
    dest_amount = models.PositiveIntegerField(default=0,
        help_text=_('amount deposited into destination in destination units'))
    dest_unit = models.CharField(max_length=3, default="usd",
        help_text=_('Measure of units on destination account'))

    # Optional
    descr = models.TextField(default="N/A")
    event_id = models.SlugField(null=True, help_text=
        _('Event at the origin of this transaction (ex. job, charge, etc.)'))

    def __unicode__(self):
        return unicode(self.id)


class NewVisitors(models.Model):
    """
    New Visitors metrics populated by reading the web server logs.
    """
    date = models.DateField(unique=True)
    visitors_number = models.PositiveIntegerField(default=0)

    def __unicode__(self):
        return unicode(self.id)


def get_current_provider():
    """
    Returns the site-wide provider from a request.
    """
    if settings.PROVIDER_CALLABLE:
        from saas.compat import import_string
        return import_string(settings.PROVIDER_CALLABLE)()
    return Organization.objects.get(pk=settings.PROVIDER_ID)


def sum_dest_amount(transactions):
    """
    Return the sum of the amount in the *transactions* set.
    """
    amount = 0
    unit = 'usd' # XXX
    if isinstance(transactions, QuerySet):
        if transactions.exists():
            queryset_unit = transactions.values('dest_unit').distinct()
            if queryset_unit.count() > 1:
                LOGGER.error(
                  "Trying to sum amounts with different units %s", transactions)
            unit = queryset_unit.first()['dest_unit']
            queryset_amount = transactions.aggregate(Sum('dest_amount'))
            amount = queryset_amount['dest_amount__sum']
    else:
        for item in transactions:
            amount += item.dest_amount
            unit = item.dest_unit      # Only works because transactions were
                                       # previously filtered by ``dest_unit``.
    return amount, unit

def sum_orig_amount(transactions):
    """
    Return the sum of the amount in the *transactions* set.
    """
    amount = 0
    unit = 'usd' # XXX
    if isinstance(transactions, QuerySet):
        if transactions.exists():
            queryset_unit = transactions.values('orig_unit').distinct()
            if queryset_unit.count() > 1:
                LOGGER.error(
                  "Trying to sum amounts with different units %s", transactions)
            unit = queryset_unit.first()['orig_unit']
            queryset_amount = transactions.aggregate(Sum('orig_amount'))
            amount = queryset_amount['orig_amount__sum']
    else:
        for item in transactions:
            amount += item.orig_amount
            unit = item.orig_unit      # Only works because transactions were
                                       # previously filtered by ``orig_unit``.
    return amount, unit
