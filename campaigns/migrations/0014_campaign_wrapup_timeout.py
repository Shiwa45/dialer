from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0013_campaign_hopper_size'),
    ]

    operations = [
        migrations.AddField(
            model_name='campaign',
            name='wrapup_timeout',
            field=models.PositiveIntegerField(default=120, help_text='Seconds an agent can remain in wrap-up before auto-available'),
        ),
    ]

