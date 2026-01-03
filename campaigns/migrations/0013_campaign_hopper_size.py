from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0012_remove_outboundqueue_disposition_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='campaign',
            name='hopper_size',
            field=models.PositiveIntegerField(default=500, help_text='Max leads to keep in the hopper/cache for this campaign'),
        ),
    ]

