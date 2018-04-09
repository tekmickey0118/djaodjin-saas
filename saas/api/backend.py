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

from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from ..mixins import OrganizationMixin
from .serializers import BankSerializer, CardSerializer

#pylint: disable=no-init
#pylint: disable=old-style-class

class RetrieveBankAPIView(OrganizationMixin, GenericAPIView):
    """
    Pass through that calls the processor API to retrieve some details about
    the deposit account associated to a provider (if that information is
    available through the :doc:`payment processor backend<backends>` API).

    This API does not trigger payment of a subscriber to a provider. Checkout
    of a subscription cart is done either through the
    :ref:`HTML page<pages_cart>` or :ref:`API end point<api_checkout>`.

    - ``balance_amount`` Amount available to transfer to the provider bank
    - ``balance_unit`` Unit of the available balance (ex: usd)
    - ``bank_name`` Name of the deposit account
    - ``last4`` Last 4 characters of the deposit account identifier

    **Example response**:

    .. sourcecode:: http

        {
          "bank_name": "Stripe Test Bank",
          "last4": "***-htrTZ",
          "balance_amount": 0,
          "balance_unit": "usd"
        }
    """
    serializer_class = BankSerializer

    def get(self, request, *args, **kwargs): #pylint: disable=unused-argument
        return Response(
            self.organization.retrieve_bank(), status=status.HTTP_200_OK)


class RetrieveCardAPIView(OrganizationMixin, GenericAPIView):
    """
    Pass through to the processor to retrieve some details about
    the payment method (ex: credit card) associated to a subscriber.

    **Example response**:

    .. sourcecode:: http

        {
          "last4": "1234",
          "exp_date": "12/2015"
        }
    """
    serializer_class = CardSerializer

    def get(self, request, *args, **kwargs): #pylint: disable=unused-argument
        return Response(
            self.organization.retrieve_card(), status=status.HTTP_200_OK)
