# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2016-11-27 04:48
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('saas', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='roledescription',
            old_name='name',
            new_name='title',
        ),
    ]