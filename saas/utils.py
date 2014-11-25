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

import datetime, random, urlparse

from django.conf import settings
from django.http.request import split_domain_port, validate_host
from django.utils.timezone import utc


def datetime_or_now(dtime_at=None):
    if not dtime_at:
        return datetime.datetime.utcnow().replace(tzinfo=utc)
    return dtime_at


def validate_redirect_url(next_url):
    """
    Returns the next_url path if next_url matches allowed hosts.
    """
    # This method is copy/pasted from signup.auth so we donot need
    # to add djaodjin-signup as a prerequisites. It is possible
    # the functionality has already moved into Django proper.
    if not next_url:
        return None
    parts = urlparse.urlparse(next_url)
    if parts.netloc:
        domain, _ = split_domain_port(parts.netloc)
        allowed_hosts = ['*'] if settings.DEBUG else settings.ALLOWED_HOSTS
        if not (domain and validate_host(domain, allowed_hosts)):
            return None
    return parts.path


def generate_random_slug(prefix=None):
    """
    This function is used, for example, to create Coupon code mechanically
    when a customer pays for the subscriptions of an organization which
    does not yet exist in the database.
    """
    suffix = "".join([random.choice("abcdefghijklmnopqrstuvwxyz0123456789-")
                      for _ in range(50)])
    if prefix:
        return str(prefix) + suffix
    return suffix


def product_url(organization, subscriber=None):
    """
    We cannot use a basic ``reverse('product_default_start')`` here because
    *organization* and ``get_current_provider`` might be different.
    """
    if subscriber:
        return '/%(organization)s/app/%(subscriber)s/' % {
            'organization': organization,
            'subscriber': subscriber}
    return '/%(organization)s/app/' % {'organization': organization}
