# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2017-03-18 13:59
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('frontend', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Competition',
            fields=[
                ('id', models.CharField(max_length=12, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=128)),
                ('year', models.IntegerField()),
                ('active', models.BooleanField(default=False)),
            ],
        ),
    ]