# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-03-15 11:37
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('survcam', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='camera',
            name='fps',
            field=models.IntegerField(default=30),
        ),
        migrations.AddField(
            model_name='camera',
            name='location',
            field=models.CharField(default='NSSL Lab 137', max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='camera',
            name='resolution',
            field=models.CharField(default='1024x768', max_length=100),
        ),
    ]