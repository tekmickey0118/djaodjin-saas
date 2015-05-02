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

"""
URLs for the saas django app
"""

from django.conf.urls import patterns, include, url

from saas.views import OrganizationRedirectView
from saas.views.billing import TransactionDownloadView
from saas.views.profile import OrganizationCreateView
from saas.settings import ACCT_REGEX


urlpatterns = patterns('',
    url(r'^app/new/', OrganizationCreateView.as_view(),
        name='saas_organization_create'),
    url(r'^billing/cart/',
        OrganizationRedirectView.as_view(pattern_name='saas_organization_cart'),
        name='saas_cart'),
    url(r'^billing/(?P<organization>%s)/download/transactions/' % ACCT_REGEX,
        TransactionDownloadView.as_view(), name='saas_transactions_download'),
    url(r'^billing/(?P<organization>%s)/' % ACCT_REGEX,
        include('saas.urls.billing')),
    url(r'^profile/', include('saas.urls.profile')),
    url(r'^users/(?P<user>%s)/' % ACCT_REGEX,
        include('saas.urls.users')),
)
