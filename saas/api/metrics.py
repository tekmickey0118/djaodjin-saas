# Copyright (c) 2015, DjaoDjin inc.
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

from django.db.models import Q
from django.utils.dateparse import parse_datetime
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from saas import settings
from saas.mixins import OrganizationMixin, ProviderMixin
from saas.models import Transaction, Organization, Plan
from saas.utils import datetime_or_now
from saas.managers.metrics import monthly_balances
from saas.api.serializers import OrganizationSerializer
from saas.managers.metrics import (
    aggregate_monthly, aggregate_monthly_transactions,
    active_subscribers, churn_subscribers)


class BalancesAPIView(OrganizationMixin, APIView):
    """
    Generate a table of revenue (rows) per months (columns).
    """

    def get(self, request, *args, **kwargs): #pylint: disable=unused-argument
        organization = self.get_organization()
        start_at = request.GET.get('start_at', None)
        if start_at:
            start_at = parse_datetime(start_at)
        start_at = datetime_or_now(start_at)
        ends_at = request.GET.get('ends_at', None)
        if ends_at:
            ends_at = parse_datetime(ends_at)
        ends_at = datetime_or_now(ends_at)
        result = []
        for key in [Transaction.INCOME, Transaction.BACKLOG,
                    Transaction.RECEIVABLE]:
            result += [{
                'key': key,
                'values': monthly_balances(organization, key, ends_at)
            }]
        return Response(result)


class RevenueMetricAPIView(OrganizationMixin, APIView):
    """
    Produce revenue stats
    """
    def get(self, request, *args, **kwargs):
        ends_at = request.GET.get('ends_at', None)
        if ends_at:
            ends_at = parse_datetime(ends_at)
        ends_at = datetime_or_now(ends_at)

        account_table, _, _ = \
            aggregate_monthly_transactions(self.get_organization(),
                Transaction.FUNDS, account_title='Payments',
                from_date=ends_at, reverse=True)

        _, refund_amount = aggregate_monthly(
            self.get_organization(), Transaction.REFUND,
            from_date=ends_at, backward=True)

        account_table += [{"key": "Refunds",
                           "values": refund_amount}]

        return Response(
            {"title": "Amount",
            "unit": "$", "scale": 0.01, "table": account_table})


class CustomerMetricAPIView(OrganizationMixin, APIView):
    """
    Produce Customer stats
    """
    def get(self, request, *args, **kwargs):
        ends_at = request.GET.get('ends_at', None)
        if ends_at:
            ends_at = parse_datetime(ends_at)
        ends_at = datetime_or_now(ends_at)

        reverse = True
        account_title = 'Payments'
        account = Transaction.FUNDS

        _, customer_table, customer_extra = \
            aggregate_monthly_transactions(self.get_organization(), account,
                account_title=account_title,
                from_date=ends_at,
                reverse=reverse)

        return Response(
            {"title": "Customers",
                "table": customer_table, "extra": customer_extra})

class PlanMetricAPIView(OrganizationMixin, APIView):
    """
    Produce Customer stats
    """

    def get(self, request, *args, **kwargs):
        ends_at = request.GET.get('ends_at', None)
        if ends_at:
            ends_at = parse_datetime(ends_at)
        ends_at = datetime_or_now(ends_at)
        organization = self.get_organization()
        table = []
        for plan in Plan.objects.filter(organization=organization):
            values = active_subscribers(
                plan, from_date=self.kwargs.get('from_date'))
            table.append({"key": plan.slug, "values": values,
                          "is_active": plan.is_active})
        extra = [{"key": "churn",
            "values": churn_subscribers(
                from_date=self.kwargs.get('from_date'))}]

        return Response(
            {"title": "Active Subscribers",
                "table": table, "extra": extra})


class OrganizationListAPIView(OrganizationMixin, GenericAPIView):

    model = Organization
    serializer_class = OrganizationSerializer
    paginate_by = 25

    def get(self, request, *args, **kwargs):
        #pylint: disable=no-member,unused-argument
        self.provider = self.get_organization()
        start_at = request.GET.get('start_at', None)
        if start_at:
            start_at = parse_datetime(start_at)
        start_at = datetime_or_now(start_at)
        ends_at = request.GET.get('ends_at', None)
        if ends_at:
            ends_at = parse_datetime(ends_at)
        ends_at = datetime_or_now(ends_at)
        queryset = self.get_range_queryset(start_at, ends_at)
        page_object_list = self.paginate_queryset(queryset)
        serializer = self.serializer_class()
        return Response({
            'start_at': start_at,
            'ends_at': ends_at,
            'count': queryset.count(),
            self.queryset_name: [serializer.to_representation(organization)
                for organization in page_object_list],
            })


class ChurnedQuerysetMixin(object):

    def get_range_queryset(self, start_time, end_time):
        return Organization.objects.filter(
            subscription__plan__organization=self.provider,
            subscription__ends_at__gte=start_time,
            subscription__ends_at__lt=end_time).order_by(
                '-subscription__ends_at', 'full_name').distinct()


class ChurnedAPIView(ChurnedQuerysetMixin, OrganizationListAPIView):

    queryset_name = 'churned'


class RegisteredQuerysetMixin(ProviderMixin):

    def get_range_queryset(self, start_time, end_time):
        #pylint: disable=unused-argument
        return Organization.objects.filter(
            Q(subscription__isnull=True) |
            Q(subscription__created_at__gte=end_time), created_at__lt=end_time
            ).exclude(pk__in=[self.provider.pk, settings.PROCESSOR_ID]
            ).order_by('-created_at', 'full_name').distinct()


class RegisteredAPIView(RegisteredQuerysetMixin, OrganizationListAPIView):

    queryset_name = 'registered'


class SubscribedQuerysetMixin(object):

    def get_range_queryset(self, start_time, end_time):
        #pylint: disable=unused-argument
        return Organization.objects.filter(
            subscription__plan__organization=self.provider,
            subscription__created_at__lt=end_time,
            subscription__ends_at__gte=end_time).order_by(
            'subscription__ends_at', 'full_name').distinct()


class SubscribedAPIView(SubscribedQuerysetMixin, OrganizationListAPIView):

    queryset_name = 'subscribed'
