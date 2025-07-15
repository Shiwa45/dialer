# Create this file: telephony/migrations/0002_asterisk_realtime_tables.py

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('telephony', '0001_initial'),
    ]

    operations = [
        # Create Asterisk PJSIP Realtime Tables
        migrations.CreateModel(
            name='PsEndpoint',
            fields=[
                ('id', models.CharField(max_length=40, primary_key=True, serialize=False)),
                ('transport', models.CharField(blank=True, default='transport-udp', max_length=40)),
                ('aors', models.CharField(max_length=200)),
                ('auth', models.CharField(max_length=40)),
                ('context', models.CharField(default='agents', max_length=40)),
                ('disallow', models.CharField(default='all', max_length=200)),
                ('allow', models.CharField(default='ulaw,alaw,gsm', max_length=200)),
                ('direct_media', models.CharField(default='no', max_length=3)),
                ('dtls_auto_generate_cert', models.CharField(blank=True, default='yes', max_length=3)),
            ],
            options={
                'db_table': 'ps_endpoints',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='PsAuth',
            fields=[
                ('id', models.CharField(max_length=40, primary_key=True, serialize=False)),
                ('auth_type', models.CharField(default='userpass', max_length=20)),
                ('password', models.CharField(max_length=80)),
                ('username', models.CharField(max_length=40)),
                ('realm', models.CharField(blank=True, max_length=40)),
            ],
            options={
                'db_table': 'ps_auths',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='PsAor',
            fields=[
                ('id', models.CharField(max_length=40, primary_key=True, serialize=False)),
                ('max_contacts', models.IntegerField(default=1)),
                ('remove_existing', models.CharField(default='yes', max_length=3)),
                ('qualify_frequency', models.IntegerField(blank=True, default=0)),
            ],
            options={
                'db_table': 'ps_aors',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='ExtensionsTable',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('context', models.CharField(max_length=40)),
                ('exten', models.CharField(max_length=40)),
                ('priority', models.IntegerField()),
                ('app', models.CharField(max_length=40)),
                ('appdata', models.CharField(max_length=256)),
            ],
            options={
                'db_table': 'extensions_table',
                'managed': True,
            },
        ),
    ]