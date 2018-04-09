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

from django.core import validators
from django.contrib.auth import get_user_model
from django.utils.translation import ugettext_lazy as _
from django.utils import six
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404

from ..decorators import _valid_manager
from ..humanize import as_money
from ..mixins import as_html_description, product_url
from ..models import (BalanceLine, CartItem, Charge, Organization, Plan,
    RoleDescription, Subscription, Transaction)
from ..utils import get_role_model

#pylint: disable=no-init,old-style-class

class EnumField(serializers.Field):
    """
    Treat a ``PositiveSmallIntegerField`` as an enum.
    """
    choices = {}
    inverted_choices = {}

    def __init__(self, choices, *args, **kwargs):
        self.choices = dict(choices)
        self.inverted_choices = {
            val: key for key, val in six.iteritems(self.choices)}
        super(EnumField, self).__init__(*args, **kwargs)

    def to_representation(self, obj):
        if isinstance(obj, list):
            result = [self.choices.get(item, None) for item in obj]
        else:
            result = self.choices.get(obj, None)
        return result

    def to_internal_value(self, data):
        if isinstance(data, list):
            result = [self.inverted_choices.get(item, None) for item in data]
        else:
            result = self.inverted_choices.get(data, None)
        if result is None:
            if not data:
                raise ValidationError("This field cannot be blank.")
            raise ValidationError(
                "'%s' is not a valid choice. Expected one of %s." % (
                data, [choice for choice in six.itervalues(self.choices)]))
        return result


class PlanRelatedField(serializers.RelatedField):

    def __init__(self, **kwargs):
        super(PlanRelatedField, self).__init__(
            queryset=Plan.objects.all(), **kwargs)

    # Django REST Framework 3.0
    def to_representation(self, obj):
        return obj.slug

    def to_internal_value(self, data):
        return get_object_or_404(Plan.objects.all(), slug=data)


class RoleDescriptionRelatedField(serializers.RelatedField):

    def __init__(self, **kwargs):
        super(RoleDescriptionRelatedField, self).__init__(**kwargs)

    # Django REST Framework 3.0
    def to_representation(self, obj):
        return obj.slug

    def to_internal_value(self, data):
        return get_object_or_404(RoleDescription.objects.all(), slug=data)


class BalanceLineSerializer(serializers.ModelSerializer):

    class Meta:
        model = BalanceLine
        fields = ('title', 'selector', 'rank')


class BankSerializer(serializers.Serializer):

    bank_name = serializers.CharField()
    last4 = serializers.CharField()
    balance_amount = serializers.IntegerField()
    balance_unit = serializers.CharField()

    def create(self, validated_data):
        raise RuntimeError('`create()` should not be called.')

    def update(self, instance, validated_data):
        raise RuntimeError('`update()` should not be called.')


class CardSerializer(serializers.Serializer):

    last4 = serializers.CharField()
    exp_date = serializers.CharField()

    def create(self, validated_data):
        raise RuntimeError('`create()` should not be called.')

    def update(self, instance, validated_data):
        raise RuntimeError('`update()` should not be called.')


class ChargeSerializer(serializers.ModelSerializer):

    state = serializers.CharField(source='get_state_display')
    readable_amount = serializers.SerializerMethodField()

    @staticmethod
    def get_readable_amount(charge):
        return as_money(charge.amount, charge.unit)

    class Meta:
        model = Charge
        fields = ('created_at', 'amount', 'unit', 'readable_amount',
                  'description', 'last4', 'exp_date', 'processor_key', 'state')


class OrganizationSerializer(serializers.ModelSerializer):

    # If we put ``slug`` in the ``read_only_fields``, it will be set ``None``
    # when one creates an opt-in subscription.
    # If we don't define ``slug`` here, the serializer validators will raise
    # an exception "Organization already exists in database".
    slug = serializers.CharField()
    email = serializers.CharField(required=False)
    printable_name = serializers.CharField(read_only=True)

    class Meta:
        model = Organization
        fields = ('slug', 'full_name', 'printable_name', 'created_at', 'email')


class WithEndsAtByPlanSerializer(serializers.Serializer):

    plan = serializers.SlugField(source='plan__slug', read_only=True)
    ends_at = serializers.DateTimeField(source='ends_at__max', read_only=True)

    class Meta:
        fields = ('plan', 'ends_at')

    def create(self, validated_data):
        raise RuntimeError('`create()` should not be called.')

    def update(self, instance, validated_data):
        raise RuntimeError('`update()` should not be called.')


class WithSubscriptionSerializer(serializers.ModelSerializer):

    plan = serializers.SlugRelatedField(read_only=True, slug_field='slug')

    class Meta:
        model = Subscription
        fields = ('created_at', 'ends_at', 'plan', 'auto_renew')


class OrganizationWithSubscriptionsSerializer(serializers.ModelSerializer):

    subscriptions = WithSubscriptionSerializer(
        source='subscription_set', many=True, read_only=True)

    class Meta:
        model = Organization
        fields = ('slug', 'full_name', 'printable_name', 'created_at',
            'email', 'subscriptions', )
        read_only_fields = ('slug', )


class OrganizationWithEndsAtByPlanSerializer(serializers.ModelSerializer):
    """
    Operational information on an Organization,
    bundled with its active subscriptions.
    """

    subscriptions = WithEndsAtByPlanSerializer(
        source='get_ends_at_by_plan', many=True, read_only=True)

    class Meta:
        model = Organization
        fields = ('slug', 'printable_name', 'created_at',
            'email', 'subscriptions', )
        read_only_fields = ('slug', )


class PlanSerializer(serializers.ModelSerializer):

    title = serializers.CharField(required=False)
    description = serializers.CharField(required=False)
    is_active = serializers.BooleanField(required=False)
    setup_amount = serializers.IntegerField(required=False)
    period_amount = serializers.IntegerField(required=False)
    interval = EnumField(choices=Plan.INTERVAL_CHOICES, required=False)
    app_url = serializers.SerializerMethodField()
    organization = serializers.SlugRelatedField(
        read_only=True, slug_field='slug')

    class Meta:
        model = Plan
        fields = ('slug', 'title', 'description', 'is_active',
                  'setup_amount', 'period_amount', 'interval', 'app_url',
                  'organization')
        read_only_fields = ('slug', 'app_url')

    @staticmethod
    def get_app_url(obj):
        return product_url(obj.organization)


class SubscriptionSerializer(serializers.ModelSerializer):

    organization = OrganizationSerializer(read_only=True)
    plan = PlanSerializer(read_only=True)
    editable = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = ('created_at', 'ends_at', 'description',
                  'organization', 'plan', 'grant_key', 'request_key',
                  'auto_renew', 'editable')
        read_only_fields = ('grant_key', 'request_key')

    def get_editable(self, subscription):
        return bool(_valid_manager(self.context['request'],
            [subscription.plan.organization]))


class TransactionSerializer(serializers.ModelSerializer):

    orig_organization = serializers.SlugRelatedField(
        read_only=True, slug_field='slug')
    dest_organization = serializers.SlugRelatedField(
        read_only=True, slug_field='slug')
    description = serializers.CharField(source='descr', read_only=True)
    amount = serializers.CharField(source='dest_amount', read_only=True)
    is_debit = serializers.CharField(source='dest_amount', read_only=True)

    def _is_debit(self, transaction):
        """
        True if the transaction can be tagged as a debit. That is
        it is either payable by the organization or the transaction
        moves from a Funds account to the organization's Expenses account.
        """
        #pylint: disable=no-member
        if ('view' in self.context
            and hasattr(self.context['view'], 'organization')):
            return transaction.is_debit(self.context['view'].organization)
        return False

    def to_representation(self, obj):
        ret = super(TransactionSerializer, self).to_representation(obj)
        is_debit = self._is_debit(obj)
        if is_debit:
            amount = as_money(obj.orig_amount, '-%s' % obj.orig_unit)
        else:
            amount = as_money(obj.dest_amount, obj.dest_unit)
        ret.update({
            'description': as_html_description(obj),
            'is_debit': is_debit,
            'amount': amount})
        return ret

    class Meta:
        model = Transaction
        fields = ('created_at', 'description', 'amount', 'is_debit',
            'orig_account', 'orig_organization', 'orig_amount', 'orig_unit',
            'dest_account', 'dest_organization', 'dest_amount', 'dest_unit')


class UserSerializer(serializers.ModelSerializer):

    # Only way I found out to remove the ``UniqueValidator``. We are not
    # interested to create new instances here.
    slug = serializers.CharField(source='username', validators=[
        validators.RegexValidator(r'^[\w.@+-]+$', _('Enter a valid username.'),
            'invalid')])
    created_at = serializers.DateTimeField(source='date_joined', required=False)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ('slug', 'email', 'full_name', 'created_at')
        read_only = ('full_name', 'created_at',)

    @staticmethod
    def get_full_name(obj):
        return obj.get_full_name()


class CartItemSerializer(serializers.ModelSerializer):
    """
    serializer for ``Coupon`` use metrics.
    """
    user = UserSerializer(required=False)
    plan = PlanRelatedField(read_only=False, required=True)

    class Meta:
        model = CartItem
        fields = ('created_at', 'user', 'plan',
            'quantity', 'first_name', 'last_name', 'sync_on')


class InvoicableSerializer(serializers.Serializer):
    """
    serializer for an invoicable item with available options.
    """
    subscription = SubscriptionSerializer(read_only=True)
    lines = TransactionSerializer(read_only=True, many=True)
    options = TransactionSerializer(read_only=True, many=True)

    def create(self, validated_data):
        raise RuntimeError('`create()` should not be called.')

    def update(self, instance, validated_data):
        raise RuntimeError('`update()` should not be called.')


class RoleDescriptionSerializer(serializers.ModelSerializer):

    organization = OrganizationSerializer(read_only=True)

    class Meta:
        model = RoleDescription
        fields = ('created_at', 'title', 'slug', 'organization', 'is_global')


class AccessibleSerializer(serializers.ModelSerializer):
    """
    Formats an entry in a list of ``Organization`` accessible by a ``User``.
    """
    slug = serializers.SlugField(source='organization.slug')
    printable_name = serializers.CharField(source='organization.printable_name')
    email = serializers.CharField(source='organization.email')
    role_description = serializers.SlugRelatedField(
        slug_field='slug', read_only=True, allow_null=True)

    class Meta:
        model = get_role_model()
        fields = ('created_at', 'request_key', 'grant_key',
            'slug', 'printable_name', 'email', # Organization
            'role_description')                # RoleDescription
        read_only_fields = ('created_at', 'request_key', 'grant_key',
            'printable_name')


class BaseRoleSerializer(serializers.ModelSerializer):

    user = UserSerializer(read_only=True)

    class Meta:
        model = get_role_model()
        fields = ('created_at', 'user', 'request_key', 'grant_key')
        read_only_fields = ('created_at', 'request_key', 'grant_key')


class RoleSerializer(BaseRoleSerializer):

    organization = OrganizationSerializer(read_only=True)
    role_description = RoleDescriptionRelatedField(read_only=True)

    class Meta(BaseRoleSerializer.Meta):
        fields = BaseRoleSerializer.Meta.fields + (
            'organization', 'role_description')
        read_only_fields = BaseRoleSerializer.Meta.read_only_fields + (
            'role_description',)
