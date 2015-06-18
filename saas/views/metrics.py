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

import json
from datetime import datetime, date, timedelta

from django.db.models import Min, Sum, Max
from django.utils.dateparse import parse_datetime
from django.utils.timezone import utc
from django.views.generic import ListView, TemplateView

from saas.api.coupons import SmartCouponListMixin
# NB: there is another CouponMixin
from saas.api.coupons import CouponMixin as CouponAPIMixin
from saas.api.metrics import (RegisteredQuerysetMixin, SubscribedQuerysetMixin,
    ChurnedQuerysetMixin)
from saas.mixins import CouponMixin, ProviderMixin, MetricsMixin
from saas.views.download import CSVDownloadView
from saas.managers.metrics import monthly_balances, month_periods
from saas.models import (CartItem, Plan, Transaction,
    NewVisitors)
from saas.compat import User
from saas.utils import datetime_or_now


class CouponMetricsView(CouponMixin, ListView):
    """
    Performance of Coupon based on CartItem.
    """

    model = CartItem
    paginate_by = 10
    template_name = 'saas/coupon_metrics.html'

    def get_queryset(self):
        queryset = super(CouponMetricsView, self).get_queryset().filter(
            coupon=self.get_coupon(), recorded=True)
        return queryset

    def get_context_data(self, **kwargs):
        context = super(CouponMetricsView, self).get_context_data(**kwargs)
        context.update({'coupon_performance_count': CartItem.objects.filter(
            coupon=self.get_coupon(), recorded=True).count()})
        return context


class CouponMetricsDownloadView(
        SmartCouponListMixin, CouponAPIMixin, ProviderMixin, CSVDownloadView):

    headings = [
        'Code',
        'Percentage',
        'Name',
        'Email',
        'Plan',
    ]

    def get_headings(self):
        return self.headings

    def get_filename(self):
        return datetime.now().strftime('coupons-%Y%m%d.csv')

    def get_queryset(self):
        '''
        Return CartItems related to the Coupon specified in the URL.
        '''
        # invoke SmartCouponListMixin to get the coupon specified by URL params
        coupons = super(CouponMetricsDownloadView, self).get_queryset()
        # get related CartItems
        return CartItem.objects.filter(coupon__in=coupons)

    def queryrow_to_columns(self, cartitem):
        return [
            cartitem.coupon.code.encode('utf-8'),
            cartitem.coupon.percent,
            ' '.join([cartitem.user.first_name, cartitem.user.last_name]).\
                encode('utf-8'),
            cartitem.user.email.encode('utf-8'),
            cartitem.plan.slug.encode('utf-8'),
        ]

class PlansMetricsView(ProviderMixin, TemplateView):
    """
    Performance of Plans for a time period
    (as a count of subscribers per plan per month)
    """

    template_name = 'saas/plan_metrics.html'

    def get_context_data(self, **kwargs):
        context = super(PlansMetricsView, self).get_context_data(**kwargs)
        tables = [
            {"title": "Active subscribers", "key": "plan", "active": True},
        ]
        context.update({
            "title": "Plans",
            "tables" : json.dumps(tables),
        })

        plans = Plan.objects.filter(organization=self.get_organization())
        context.update({"plans": plans})
        return context


class RevenueMetricsView(MetricsMixin, TemplateView):
    """
    Generate a table of revenue (rows) per months (columns).
    """

    template_name = 'saas/metrics_base.html'

    def get_context_data(self, **kwargs):
        context = super(RevenueMetricsView, self).get_context_data(**kwargs)
        tables = [
            {"title": "Amount", "key": "revenue", "active": True},
            {"title": "Customers", "key": "customer"},
        ]
        context.update({
            "title": "Revenue",
            "tables": json.dumps(tables)
        })
        return context


class BalancesMetricsView(MetricsMixin, TemplateView):
    """
    Display balances.
    """

    template_name = 'saas/metrics_balances.html'

    def get_context_data(self, **kwargs):
        context = super(BalancesMetricsView, self).get_context_data(**kwargs)
        context.update({'title': 'Balances'})
        return context


class BalancesDownloadView(MetricsMixin, CSVDownloadView):
    """
    Export balance metrics as a CSV file.
    """
    queryname = 'balances'

    def get_headings(self):
        return ['name'] + [
            end_period for end_period in month_periods(from_date=self.ends_at)]

    def get_filename(self, *_):
        return '{}.csv'.format(self.queryname)

    def get(self, request, *args, **kwargs): #pylint: disable=unused-argument
        # cache_fields sets attributes like 'starts_at',
        # required by other methods
        self.cache_fields(request)
        return super(BalancesDownloadView, self).get(request, *args, **kwargs)

    def get_queryset(self, *_):
        return Transaction.objects.distinct_accounts()

    def queryrow_to_columns(self, account):
        return [account] + [item[1] for item in monthly_balances(
            self.organization, account, self.ends_at)]

class SubscriberPipelineView(ProviderMixin, TemplateView):

    template_name = "saas/subscriber_pipeline.html"


class AbstractSubscriberPipelineDownloadView(ProviderMixin, CSVDownloadView):

    subscriber_type = None

    def get(self, request, *args, **kwargs):
        self.provider = self.get_organization()
        self.start_date = datetime_or_now(
            parse_datetime(request.GET.get('start_date', None).strip('"')))
        self.end_date = datetime_or_now(
            parse_datetime(request.GET.get('end_date', None).strip('"')))

        return super(AbstractSubscriberPipelineDownloadView, self).get(
            request, *args, **kwargs)

    def get_range_queryset(self, start_date, end_date):
        raise NotImplementedError()

    def get_queryset(self):
        return self.get_range_queryset(self.start_date, self.end_date)

    def get_headings(self):
        return ['Name', 'Email', 'Registration Date']

    def get_filename(self):
        return 'subscribers-{}-{}.csv'.format(
            self.subscriber_type, datetime.now().strftime('%Y%m%d'))

    def queryrow_to_columns(self, org):
        return [
            org.full_name.encode('utf-8'),
            org.email.encode('utf-8'),
            org.created_at,
        ]


class SubscriberPipelineRegisteredDownloadView(
        RegisteredQuerysetMixin, AbstractSubscriberPipelineDownloadView):

    subscriber_type = 'registered'


class SubscriberPipelineSubscribedDownloadView(
        SubscribedQuerysetMixin, AbstractSubscriberPipelineDownloadView):

    subscriber_type = 'subscribed'


class SubscriberPipelineChurnedDownloadView(
        ChurnedQuerysetMixin, AbstractSubscriberPipelineDownloadView):

    subscriber_type = 'churned'


class UsageMetricsView(ProviderMixin, TemplateView):

    template_name = "saas/usage_chart.html"

    def get_context_data(self, **kwargs):
        context = super(UsageMetricsView, self).get_context_data(**kwargs)
        organization = self.get_organization()
        # Note: There is a way to get the result in a single SQL statement
        # but that requires to deal with differences in databases
        # (MySQL: date_format, SQLite: strftime) and get around the
        # "Raw query must include the primary key" constraint.
        values = []
        today = date.today()
        end = datetime(day=today.day, month=today.month, year=today.year,
                                tzinfo=utc)
        for _ in range(0, 12):
            first = datetime(day=1, month=end.month, year=end.year,
                                      tzinfo=utc)
            usages = Transaction.objects.filter(
                orig_organization=organization, orig_account='Usage',
                created_at__lt=first).aggregate(Sum('amount'))
            amount = usages.get('amount__sum', 0)
            if not amount:
                # The key could be associated with a "None".
                amount = 0
            values += [{"x": date.strftime(first, "%Y/%m/%d"), "y": amount}]
            end = first - timedelta(days=1)
        context.update({'data': [{"key": "Usage", "values": values}]})
        return context


class OverallMetricsView(TemplateView):

    template_name = "saas/general_chart.html"

    def get_context_data(self, **kwargs):
        all_values = []
        for organization in self.request.user.manages.all():
            values = []
            today = date.today()
            end = datetime(day=today.day, month=today.month, year=today.year,
                                    tzinfo=utc)
            for _ in range(0, 12):
                first = datetime(day=1, month=end.month, year=end.year,
                                          tzinfo=utc)
                usages = Transaction.objects.filter(
                    orig_organization=organization, orig_account='Usage',
                    created_at__lt=first).aggregate(Sum('amount'))
                amount = usages.get('amount__sum', 0)
                if not amount:
                    # The key could be associated with a "None".
                    amount = 0
                values += [{"x": date.strftime(first, "%Y/%m/%d"),
                            "y": amount}]
                end = first - timedelta(days=1)
            all_values += [{
                "key": str(organization.slug), "values": values}]
        context = {'data' : all_values}
        return context


class VisitorsView(TemplateView):
    """
    Number of visitors as measured by the website logs.
    """

    template_name = 'saas/stat.html'

    def get_context_data(self, **kwargs):
        #pylint: disable=too-many-locals
        context = super(VisitorsView, self).get_context_data(**kwargs)
        min_date = NewVisitors.objects.all().aggregate(Min('date'))
        max_date = NewVisitors.objects.all().aggregate(Max('date'))
        min_date = min_date.get('date__min', 0)
        max_date = max_date.get('date__max', 0)
        date_tabl = [{"x": datetime.strftime(new.date, "%Y/%m/%d"),
                      "y": new.visitors_number / 5}
                     for new in NewVisitors.objects.all()]
        current_date = min_date
        delta = timedelta(days=1)
        while current_date <= max_date:
            j = len(date_tabl)
            tbl = []
            for i in range(j):
                if date_tabl[i]["x"] == datetime.strftime(
                    current_date, "%Y/%m/%d"):
                    tbl += [i]
            if len(tbl) == 0:
                date_tabl += [{
                    "x": datetime.strftime(current_date, "%Y/%m/%d"), "y": 0}]
            current_date += delta

        date_tabl.sort()

        ########################################################
        # Conversion visitors to trial
        date_joined_username = []
        for user in User.objects.all():
            if (datetime.strftime(user.date_joined, "%Y/%m/%d")
                > datetime.strftime(min_date, "%Y/%m/%d") and
                datetime.strftime(user.date_joined, "%Y/%m/%d")
                < datetime.strftime(max_date, "%Y/%m/%d")):
                date_joined_username += [{
                        "date": user.date_joined, "user": str(user.username)}]

        user_per_joined_date = {}
        for datas in date_joined_username:
            key = datas["date"]
            if not key in user_per_joined_date:
                user_per_joined_date[key] = []
            user_per_joined_date[key] += [datas["user"]]

        trial = []
        for joined_at in user_per_joined_date.keys():
            trial += [{
                "x": joined_at, "y": len(user_per_joined_date[joined_at])}]

        min_date_trial = User.objects.all().aggregate(Min('date_joined'))
        max_date_trial = User.objects.all().aggregate(Max('date_joined'))
        min_date_trial = min_date_trial.get('date_joined__min', 0)
        max_date_trial = max_date_trial.get('date_joined__max', 0)

        for item in trial:
            item["x"] = datetime.strftime(item["x"], "%Y/%m/%d")
        curr_date = min_date
        delta = timedelta(days=1)
        while curr_date <= max_date:
            j = len(trial)
            count = 0
            for i in range(j):
                if trial[i]["x"] == datetime.strftime(curr_date, "%Y/%m/%d"):
                    count += 1
            if count == 0:
                trial += [{
                    "x": datetime.strftime(curr_date, "%Y/%m/%d"), "y": 0}]
            curr_date += delta
        trial.sort()

        context = {'data' : [{"key": "Signup number",
                              "color": "#d62728",
                              "values": trial},
                             {"key": "New visitor number",
                              "values": date_tabl}]}
        return context
