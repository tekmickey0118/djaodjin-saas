# Copyright (c) 2022, DjaoDjin inc.
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
URLs for API related to users accessible by.
"""

from ... import settings
from ...api.roles import (AccessibleByListAPIView, AccessibleDetailAPIView,
    RoleAcceptAPIView, AccessibleByDescrListAPIView, UserProfileListAPIView)
from ...compat import path, re_path

urlpatterns = [
    re_path(
        r'^users/(?P<user>%s)/accessibles/accept/(?P<verification_key>%s)' % (
        settings.SLUG_RE, settings.VERIFICATION_KEY_RE),
        RoleAcceptAPIView.as_view(), name='saas_api_accessibles_accept'),
    path('users/<slug:user>/accessibles/<slug:role>/<slug:%s>' %
        settings.PROFILE_URL_KWARG,
        AccessibleDetailAPIView.as_view(), name='saas_api_accessible_detail'),
    path('users/<slug:user>/accessibles/<slug:role>',
        AccessibleByDescrListAPIView.as_view(),
        name='saas_api_accessibles_by_descr'),
    path('users/<slug:user>/accessibles',
        AccessibleByListAPIView.as_view(), name='saas_api_accessibles'),
    path('users/<slug:user>/profiles',
        UserProfileListAPIView.as_view(), name='saas_api_user_profiles'),
]
