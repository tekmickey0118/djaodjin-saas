# Copyright (c) 2013, Fortylines LLC
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions and the following disclaimer in the documentation
#     and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
Convenience module for access of saas application settings, which enforces
default settings when the main settings module does not contain
the appropriate settings.
"""
from django.conf import settings

SITE_ID = getattr(settings, 'SAAS_SITE_ID', getattr(settings, 'SITE_ID', 1))

CREDIT_ON_CREATE = getattr(settings, 'SAAS_CREDIT_ON_CREATE', 1000)

CONTRIBUTOR_RELATION = getattr(settings, 'SAAS_CONTRIBUTOR_RELATION', None)
MANAGER_RELATION = getattr(settings, 'SAAS_MANAGER_RELATION', None)

PROCESSOR_HOOK_URL = getattr(settings, 'SAAS_PROCESSOR_HOOK_URL', "postevent")

STRIPE_PRIV_KEY = getattr(settings, 'STRIPE_PRIV_KEY', "Undefined")
STRIPE_PUB_KEY = getattr(settings, 'STRIPE_PUB_KEY', "Undefined")

ACCT_REGEX   = r'[a-zA-Z0-9_\-]+'

