from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agentstatus',
            name='status',
            field=models.CharField(choices=[('offline', 'Offline'), ('available', 'Available'), ('busy', 'Busy'), ('wrapup', 'Wrap-up'), ('break', 'Break'), ('lunch', 'Lunch'), ('training', 'Training'), ('meeting', 'Meeting'), ('system_issues', 'System Issues')], default='offline', max_length=20),
        ),
    ]
