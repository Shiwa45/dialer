from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0009_campaign_outbound_carrier'),
        ('leads', '0003_leadimport_field_mapping'),
    ]

    operations = [
        migrations.AddField(
            model_name='leadlist',
            name='assigned_campaign',
            field=models.ForeignKey(blank=True, help_text='If set, leads in this list will be auto-queued to the campaign.', null=True, on_delete=models.SET_NULL, related_name='lead_lists', to='campaigns.campaign'),
        ),
    ]
