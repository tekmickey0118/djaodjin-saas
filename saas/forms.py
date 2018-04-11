# Copyright (c) 2018, DjaoDjin inc.
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

"""
Forms shown by the saas application
"""

from decimal import Decimal

from django import forms
from django.template.defaultfilters import slugify
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _
from django_countries import countries
from django_countries.fields import Country
import localflavor.us.forms as us_forms

from .models import Organization, Plan, Subscription

#pylint: disable=super-on-old-class,no-member
#pylint: disable=old-style-class,no-init

class BankForm(forms.ModelForm):
    """
    Update Bank Information
    """
    form_id = 'bank-form'
    stripeToken = forms.CharField(
        required=False, widget=forms.widgets.HiddenInput())

    class Meta:
        model = Organization
        fields = tuple([])


class PostalFormMixin(object):

    def add_postal_country(self, field_name='country', required=True):
        self.fields[field_name] = forms.CharField(
            widget=forms.widgets.Select(choices=countries),
            label='Country', required=required)

    def add_postal_region(self, field_name='region',
                          country=None, required=True):
        if country and country.code == "US":
            widget = us_forms.USPSSelect
        else:
            widget = forms.widgets.TextInput
        if field_name in self.fields:
            self.fields[field_name].widget = widget()
        else:
            self.fields[field_name] = forms.CharField(
                widget=widget, label='State/Province/County', required=required)



class CreditCardForm(PostalFormMixin, forms.Form):
    """
    Update Card Information.
    """
    stripeToken = forms.CharField(required=False)
    razorpay_payment_id = forms.CharField(required=False)
    remember_card = forms.BooleanField(
        label=_("Remember this card"), required=False, initial=True)

    def __init__(self, *args, **kwargs):
        #call our superclasse's initializer
        super(CreditCardForm, self).__init__(*args, **kwargs)
        #define other fields dynamically:
        self.fields['card_name'] = forms.CharField(
            label='Card Holder', required=False)
        self.fields['card_city'] = forms.CharField(
            label='City', required=False)
        self.fields['card_address_line1'] = forms.CharField(
            label='Street', required=False)
        self.add_postal_region(country=self.initial['country'], required=False)
        self.fields['card_address_zip'] = forms.CharField(
            label='Zip/Postal Code', required=False)
        self.add_postal_country(required=False)
        for item in self.initial:
            if item.startswith('cart-'):
                self.fields[item] = forms.CharField(required=True)

    def clean_remember_card(self):
        remember_card = self.data.get('remember_card', None)
        if remember_card is not None:
            self.cleaned_data['remember_card'] = (
                remember_card != "0" and remember_card != "off")
        return self.cleaned_data['remember_card']


class VTChargeForm(CreditCardForm):

    amount = forms.CharField()
    descr = forms.CharField()

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        try:
            self.cleaned_data['amount'] = int(Decimal(amount) * 100)
        except (TypeError, ValueError) as err:
            raise forms.ValidationError("'%s' is an invalid amount (%s)"
                % (amount, err))
        return self.cleaned_data['amount']


class CartPeriodsForm(forms.Form):

    def __init__(self, *args, **kwargs):
        super(CartPeriodsForm, self).__init__(*args, **kwargs)
        for item in self.initial:
            if item.startswith('cart-'):
                self.fields[item] = forms.CharField(required=True)


class ImportTransactionForm(forms.Form):

    subscription = forms.CharField()
    created_at = forms.DateTimeField()
    amount = forms.DecimalField()
    descr = forms.CharField(required=False)

    def clean_subscription(self):
        parts = self.cleaned_data['subscription'].split(Subscription.SEP)
        if len(parts) != 2:
            raise forms.ValidationError(
                "subscription should be of the form subscriber:plan")
        return self.cleaned_data['subscription']

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        try:
            self.cleaned_data['amount'] = int(Decimal(amount) * 100)
        except (TypeError, ValueError):
            raise forms.ValidationError("invalid amount")
        return self.cleaned_data['amount']



class OrganizationForm(PostalFormMixin, forms.ModelForm):

    submit_title = 'Update'
    street_address = forms.CharField(required=False)
    phone = forms.CharField(required=False)

    class Meta:
        model = Organization
        fields = ('full_name', 'email', 'phone', 'country',
                  'region', 'locality', 'street_address', 'postal_code')
        widgets = {'country': forms.widgets.Select(choices=countries)}

    def __init__(self, *args, **kwargs):
        super(OrganizationForm, self).__init__(*args, **kwargs)
        if kwargs.get('instance', None) is None:
            self.submit_title = 'Create'
        if 'country' in self.fields:
            # Country field is optional. We won't add a State/Province
            # in case it is omitted.
            if not ('country' in self.initial
                and self.initial['country']):
                self.initial['country'] = Country("US", None)
            country = self.initial.get('country', None)
            if self.instance and self.instance.country:
                country = self.instance.country
            if not self.fields['country'].initial:
                self.fields['country'].initial = country.code
            self.add_postal_region(country=country)
        if 'is_bulk_buyer' in self.initial:
            initial = self.initial['is_bulk_buyer']
            if self.instance:
                initial = self.instance.is_bulk_buyer
            self.fields['is_bulk_buyer'] = forms.BooleanField(required=False,
                initial=initial,
                label=mark_safe('Enable GroupBuy '\
'(<a href="/docs/#group-billing" target="_blank">what is it?</a>)'))
        if 'extra' in self.initial:
            initial = self.initial['extra']
            if self.instance:
                initial = self.instance.extra
            self.fields['extra'] = forms.CharField(required=False,
                widget=forms.Textarea, label=mark_safe('Notes'),
                initial=initial)


class OrganizationCreateForm(OrganizationForm):

    slug = forms.SlugField(label="ShortID",
        help_text=_("Unique identifier shown in the URL bar."))

    class Meta:
        model = Organization
        fields = ('slug', 'full_name', 'email')


class ManagerAndOrganizationForm(OrganizationForm):

    def __init__(self, *args, **kwargs):
        super(ManagerAndOrganizationForm, self).__init__(*args, **kwargs)
        self.fields['full_name'].label = 'Full name'
        # XXX define other fields dynamically (username, etc.):
        # Unless it is not necessary?


class PlanForm(forms.ModelForm):
    """
    Form to create or update a ``Plan``.
    """
    submit_title = 'Update'

    unit = forms.ChoiceField(choices=(
        ('usd', 'usd'), ('cad', 'cad'), ('eur', 'eur')))
    period_amount = forms.DecimalField(max_digits=7, decimal_places=2)
    advance_discount = forms.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        model = Plan
        fields = ('title', 'description', 'period_amount', 'unit', 'interval',
                  'period_length', 'advance_discount',
                  'auto_renew', 'is_not_priced')

    def __init__(self, initial=None, instance=None, *args, **kwargs):
        if initial:
            period_amount = initial.get('period_amount', 0)
            advance_discount = initial.get('advance_discount', 0)
        if instance:
            period_amount = instance.period_amount
            advance_discount = instance.advance_discount
        else:
            self.submit_title = 'Create'
        period_amount = Decimal(period_amount).scaleb(-2)
        advance_discount = Decimal(advance_discount).scaleb(-2)
        initial.update({
            'period_amount':period_amount,
            'advance_discount': advance_discount})
        super(PlanForm, self).__init__(
            initial=initial, instance=instance, *args, **kwargs)

    def clean_advance_discount(self):
        try:
            self.cleaned_data['advance_discount'] = \
              int(self.cleaned_data['advance_discount'].scaleb(2))
        except (TypeError, ValueError):
            self.cleaned_data['advance_discount'] = 0
        return self.cleaned_data['advance_discount']

    def clean_period_amount(self):
        try:
            self.cleaned_data['period_amount'] = \
              int(self.cleaned_data['period_amount'].scaleb(2))
        except (TypeError, ValueError):
            self.cleaned_data['period_amount'] = 0
        return self.cleaned_data['period_amount']

    def clean_title(self):
        kwargs = {}
        if 'organization' in self.initial:
            kwargs.update({'organization': self.initial['organization']})
        try:
            exists = Plan.objects.get(
                slug=slugify(self.cleaned_data['title']), **kwargs)
            if self.instance is None or exists.pk != self.instance.pk:
                # Rename is ok.
                raise forms.ValidationError(
                    _("A Plan with this title already exists."))
        except Plan.DoesNotExist:
            pass
        return self.cleaned_data['title']

    def save(self, commit=True):
        if 'organization' in self.initial:
            self.instance.organization = self.initial['organization']
        return super(PlanForm, self).save(commit)


class RedeemCouponForm(forms.Form):
    """
    Form used to redeem a coupon.
    """
    submit_title = 'Redeem'

    code = forms.CharField(label="Registration code")


class UserRelationForm(forms.Form):
    """
    Form to add/remove managers and other custom roles.
    """
    username = forms.CharField()


class WithdrawForm(BankForm):
    """
    Withdraw amount from ``Funds`` to a bank account
    """
    submit_title = 'Withdraw'
    amount = forms.DecimalField(label="Amount (in $)", required=False)
