from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0010_remove_campaign_outbound_trunk_and_more'),
        ('campaigns', '0004_outboundqueue'),
    ]

    operations = [
        migrations.AddField(
            model_name='outboundqueue',
            name='disposition',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='outboundqueue',
            name='wrapup_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

