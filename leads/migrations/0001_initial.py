# Generated by Django 5.0.7 on 2025-07-04 12:44

import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('campaigns', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DNCList',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=200)),
                ('dnc_type', models.CharField(choices=[('internal', 'Internal DNC'), ('campaign', 'Campaign Specific'), ('federal', 'Federal DNC'), ('state', 'State DNC'), ('custom', 'Custom List')], default='internal', max_length=20)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'DNC List',
                'verbose_name_plural': 'DNC Lists',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Lead',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('lead_id', models.CharField(default=uuid.uuid4, max_length=50, unique=True)),
                ('first_name', models.CharField(max_length=100)),
                ('last_name', models.CharField(max_length=100)),
                ('middle_name', models.CharField(blank=True, max_length=100)),
                ('title', models.CharField(blank=True, max_length=50)),
                ('phone_number', models.CharField(max_length=20, validators=[django.core.validators.RegexValidator(message='Enter a valid phone number', regex='^\\+?1?\\d{9,15}$')])),
                ('alt_phone', models.CharField(blank=True, max_length=20)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('address1', models.CharField(blank=True, max_length=200)),
                ('address2', models.CharField(blank=True, max_length=200)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state', models.CharField(blank=True, max_length=50)),
                ('postal_code', models.CharField(blank=True, max_length=20)),
                ('country', models.CharField(default='US', max_length=100)),
                ('status', models.CharField(choices=[('new', 'New'), ('called', 'Called'), ('callback', 'Callback Scheduled'), ('interested', 'Interested'), ('not_interested', 'Not Interested'), ('sale', 'Sale'), ('dnc', 'Do Not Call'), ('invalid', 'Invalid')], default='new', max_length=20)),
                ('priority', models.PositiveIntegerField(default=1)),
                ('call_count', models.PositiveIntegerField(default=0)),
                ('last_called', models.DateTimeField(blank=True, null=True)),
                ('next_call_time', models.DateTimeField(blank=True, null=True)),
                ('best_time_to_call', models.CharField(blank=True, max_length=100)),
                ('timezone', models.CharField(default='UTC', max_length=50)),
                ('comments', models.TextField(blank=True)),
                ('source', models.CharField(blank=True, max_length=200)),
                ('custom_fields', models.JSONField(blank=True, default=dict)),
                ('is_dnc', models.BooleanField(default=False)),
                ('is_callback', models.BooleanField(default=False)),
                ('is_priority', models.BooleanField(default=False)),
                ('assigned_agent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_leads', to=settings.AUTH_USER_MODEL)),
                ('assigned_campaign', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='campaign_leads', to='campaigns.campaign')),
            ],
            options={
                'verbose_name': 'Lead',
                'verbose_name_plural': 'Leads',
                'ordering': ['priority', 'last_called'],
            },
        ),
        migrations.CreateModel(
            name='LeadHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('action_type', models.CharField(choices=[('created', 'Lead Created'), ('called', 'Call Made'), ('status_change', 'Status Changed'), ('assigned', 'Agent Assigned'), ('note_added', 'Note Added'), ('imported', 'Lead Imported'), ('callback_scheduled', 'Callback Scheduled')], max_length=20)),
                ('description', models.TextField()),
                ('old_value', models.TextField(blank=True)),
                ('new_value', models.TextField(blank=True)),
                ('lead', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='history', to='leads.lead')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Lead History',
                'verbose_name_plural': 'Lead Histories',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='LeadList',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('list_id', models.CharField(default=uuid.uuid4, max_length=50, unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('source_file', models.CharField(blank=True, max_length=500)),
                ('import_date', models.DateTimeField(blank=True, null=True)),
                ('total_leads', models.PositiveIntegerField(default=0)),
                ('active_leads', models.PositiveIntegerField(default=0)),
                ('called_leads', models.PositiveIntegerField(default=0)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='created_lead_lists', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Lead List',
                'verbose_name_plural': 'Lead Lists',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='LeadImport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed'), ('cancelled', 'Cancelled')], default='pending', max_length=20)),
                ('file_name', models.CharField(max_length=500)),
                ('file_path', models.CharField(max_length=1000)),
                ('file_size', models.PositiveIntegerField(default=0)),
                ('skip_duplicates', models.BooleanField(default=True)),
                ('update_existing', models.BooleanField(default=False)),
                ('field_mapping', models.JSONField(default=dict)),
                ('total_rows', models.PositiveIntegerField(default=0)),
                ('processed_rows', models.PositiveIntegerField(default=0)),
                ('imported_leads', models.PositiveIntegerField(default=0)),
                ('skipped_leads', models.PositiveIntegerField(default=0)),
                ('error_count', models.PositiveIntegerField(default=0)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('error_log', models.TextField(blank=True)),
                ('started_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('lead_list', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='imports', to='leads.leadlist')),
            ],
            options={
                'verbose_name': 'Lead Import',
                'verbose_name_plural': 'Lead Imports',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='lead',
            name='lead_list',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='leads', to='leads.leadlist'),
        ),
        migrations.CreateModel(
            name='LeadNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('note', models.TextField()),
                ('is_important', models.BooleanField(default=False)),
                ('lead', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notes', to='leads.lead')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Lead Note',
                'verbose_name_plural': 'Lead Notes',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DNCEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('phone_number', models.CharField(max_length=20, validators=[django.core.validators.RegexValidator(message='Enter a valid phone number', regex='^\\+?1?\\d{9,15}$')])),
                ('reason', models.CharField(blank=True, max_length=200)),
                ('expires_on', models.DateField(blank=True, null=True)),
                ('added_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('dnc_list', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='entries', to='leads.dnclist')),
            ],
            options={
                'verbose_name': 'DNC Entry',
                'verbose_name_plural': 'DNC Entries',
                'indexes': [models.Index(fields=['phone_number'], name='leads_dncen_phone_n_3d80a6_idx')],
                'unique_together': {('dnc_list', 'phone_number')},
            },
        ),
        migrations.CreateModel(
            name='CallbackSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('scheduled_time', models.DateTimeField()),
                ('timezone', models.CharField(default='UTC', max_length=50)),
                ('is_completed', models.BooleanField(default=False)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('reminder_sent', models.BooleanField(default=False)),
                ('agent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scheduled_callbacks', to=settings.AUTH_USER_MODEL)),
                ('campaign', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scheduled_callbacks', to='campaigns.campaign')),
                ('lead', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='callbacks', to='leads.lead')),
            ],
            options={
                'verbose_name': 'Callback Schedule',
                'verbose_name_plural': 'Callback Schedules',
                'ordering': ['scheduled_time'],
                'indexes': [models.Index(fields=['scheduled_time'], name='leads_callb_schedul_028e92_idx'), models.Index(fields=['agent', 'is_completed'], name='leads_callb_agent_i_dede0b_idx')],
            },
        ),
        migrations.AddIndex(
            model_name='lead',
            index=models.Index(fields=['phone_number'], name='leads_lead_phone_n_e78ed0_idx'),
        ),
        migrations.AddIndex(
            model_name='lead',
            index=models.Index(fields=['status'], name='leads_lead_status_e23abe_idx'),
        ),
        migrations.AddIndex(
            model_name='lead',
            index=models.Index(fields=['last_called'], name='leads_lead_last_ca_508e1b_idx'),
        ),
        migrations.AddIndex(
            model_name='lead',
            index=models.Index(fields=['assigned_agent'], name='leads_lead_assigne_4b518a_idx'),
        ),
    ]
