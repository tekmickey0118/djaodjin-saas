djaodjin-saas is a Django application that implements the logic to support
subscription-based Sofware-as-a-Service businesses.

Major Features:

- Separate billing profiles and authenticated users
- Double entry book keeping ledger
- Flexible security framework

Full documentation for the project is available at [Read-the-Docs](http://djaodjin-saas.readthedocs.org/)

Development
===========

After cloning the repository, create a virtualenv environment, install
the prerequisites, create and load initial data into the database, then
run the testsite webapp.

    $ virtualenv-2.7 _installTop_
    $ source _installTop_/bin/activate
    $ pip install -r requirements.txt -r testsite/requirements.txt
    $ make initdb
    $ python manage.py runserver

    # Browse http://localhost:8000/
    # Login with username: donny and password: yoyo

To test payment through [Stripe](https://stripe.com/):

1. Verify the Stripe API version you are using in the Stripe dashboard.

    API Version: 2014-03-28

2. Add your Stripe keys in the credentials file.

    # Authentication with payment provider
    STRIPE_PUB_KEY = "_your_stripe_public_api_key_"
    STRIPE_PRIV_KEY = "_your_stripe_private_api_key_"
