# users/migrations/0013_agentstatus_heartbeat_timelog.py
# Generated migration - adds AgentTimeLog model + heartbeat/wrapup tracking to AgentStatus

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0012_remove_agentstatus_call_duration_seconds_and_more'),
        ('calls', '0003_calllog_amd_action_calllog_amd_result_and_more'),
        ('campaigns', '0001_initial'),
    ]

    operations = [
        # ── Add heartbeat + wrapup tracking to AgentStatus ──────────────
        migrations.AddField(
            model_name='agentstatus',
            name='last_heartbeat',
            field=models.DateTimeField(
                null=True, blank=True,
                help_text='Last ping from agent browser - used for zombie detection'
            ),
        ),
        migrations.AddField(
            model_name='agentstatus',
            name='wrapup_started_at',
            field=models.DateTimeField(
                null=True, blank=True,
                help_text='When agent entered wrapup status'
            ),
        ),
        migrations.AddField(
            model_name='agentstatus',
            name='wrapup_call_id',
            field=models.CharField(
                max_length=50, blank=True, default='',
                help_text='Call ID pending disposition in wrapup'
            ),
        ),

        # ── AgentTimeLog model ───────────────────────────────────────────
        migrations.CreateModel(
            name='AgentTimeLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(
                    max_length=20,
                    choices=[
                        ('offline', 'Offline'),
                        ('available', 'Available'),
                        ('busy', 'Busy/On Call'),
                        ('wrapup', 'Wrap-up'),
                        ('break', 'Break'),
                        ('lunch', 'Lunch'),
                        ('training', 'Training'),
                        ('meeting', 'Meeting'),
                        ('system_issues', 'System Issues'),
                    ],
                    db_index=True,
                )),
                ('started_at', models.DateTimeField()),
                ('ended_at', models.DateTimeField(null=True, blank=True)),
                ('duration_seconds', models.PositiveIntegerField(default=0)),
                ('date', models.DateField(db_index=True)),
                ('notes', models.CharField(max_length=200, blank=True, default='')),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='time_logs',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('call_log', models.ForeignKey(
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='time_logs',
                    to='calls.calllog',
                )),
                ('campaign', models.ForeignKey(
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='agent_time_logs',
                    to='campaigns.campaign',
                )),
            ],
            options={
                'verbose_name': 'Agent Time Log',
                'verbose_name_plural': 'Agent Time Logs',
                'ordering': ['-started_at'],
                'indexes': [
                    models.Index(fields=['user', 'date'], name='users_timelog_user_date_idx'),
                    models.Index(fields=['user', 'status', 'date'], name='users_timelog_usr_stat_dt_idx'),
                ],
            },
        ),
    ]
