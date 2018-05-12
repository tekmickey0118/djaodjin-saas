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
URLs API for resources available typically only to the broker platform.
"""

from django.conf.urls import url

from ... import settings
from ...api.balances import BalanceLineListAPIView, BrokerBalancesAPIView
from ...api.charges import ChargeListAPIView
from ...api.transactions import (CancelStatementBalanceAPIView,
    TransactionListAPIView)
from ...api.users import RegisteredAPIView, UserListAPIView


urlpatterns = [
    url(r'^billing/transactions/?',
        TransactionListAPIView.as_view(), name='saas_api_transactions'),
    url(r'^billing/(?P<organization>%s)/balance/cancel/?' % settings.ACCT_REGEX,
        CancelStatementBalanceAPIView.as_view(),
        name='saas_api_cancel_balance_due'),
    url(r'^billing/charges/?$', ChargeListAPIView.as_view(),
        name='saas_api_charges'),
    url(r'^metrics/balances/(?P<report>%s)/?' % settings.ACCT_REGEX,
        BrokerBalancesAPIView.as_view(), name='saas_api_broker_balances'),
    url(r'^metrics/lines/(?P<report>%s)/?' % settings.ACCT_REGEX,
        BalanceLineListAPIView.as_view(), name='saas_api_balance_lines'),
    url(r'^metrics/registered/?',
        RegisteredAPIView.as_view(), name='saas_api_registered'),
    url(r'^users/?',
        UserListAPIView.as_view(), name='saas_api_users'),
]
