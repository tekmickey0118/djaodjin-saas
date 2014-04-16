# Copyright (c) 2014, Fortylines LLC
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

import datetime, re

from django.utils.timezone import utc

DESCRIBE_BALANCE = \
    "Balance on %(plan)s"

DESCRIBE_BUY_PERIODS = \
    "Subscription to %(plan)s until %(ends_at)s (%(humanized_periods)s)"

DESCRIBE_CHARGED_CARD = \
    "Charge %(charge)s on credit card of %(organization)s"

DESCRIBE_UNLOCK_NOW = \
    "Unlock %(plan)s now. Don't worry later to %(unlock_event)s."

DESCRIBE_UNLOCK_LATER = \
    "Access %(plan)s Today. Pay %(amount)s later to %(unlock_event)s."


def as_buy_periods(descr):
    """
    Returns a triplet (plan, ends_at, nb_periods) from a string
    formatted with DESCRIBE_BUY_PERIODS.
    """
    from saas.models import Plan
    plan = None
    nb_periods = 0
    ends_at = datetime.datetime()
    look = re.match(DESCRIBE_BUY_PERIODS % {
            'plan': r'(?P<plan>\S+)',
            'ends_at': r'(?P<ends_at>\d\d\d\d/\d\d/\d\d)',
            'humanized_periods': r'(?P<nb_periods>\d+).*'}, descr)
    if look:
        try:
            plan = Plan.objects.get(slug=look.group('plan'))
        except Plan.DoesNotExist:
            plan = None
        ends_at = datetime.datetime.strptime(
            look.group('ends_at'), '%Y/%m/%d').replace(tzinfo=utc)
        nb_periods = int(look.group('nb_periods'))
    return (plan, ends_at, nb_periods)


def as_money(value):
    if not value:
        return '$0.00'
    return '$%.2f' % (float(value) / 100)
    # XXX return locale.currency(value, grouping=True)


def describe_buy_periods(plan, ends_at, nb_periods):
    return (DESCRIBE_BUY_PERIODS %
            {'plan': plan,
             'ends_at': datetime.datetime.strftime(ends_at, '%Y/%m/%d'),
             'humanized_periods': plan.humanize_period(nb_periods)})


def match_unlock(descr):
    look = re.match(DESCRIBE_UNLOCK_NOW % {
            'plan': r'(?P<plan>\S+)', 'unlock_event': r'.*'}, descr)
    if not look:
        look = re.match(DESCRIBE_UNLOCK_LATER % {
            'plan': r'(?P<plan>\S+)', 'unlock_event': r'.*',
            'amount': r'.*'}, descr)
    if not look:
        return False
    return True
