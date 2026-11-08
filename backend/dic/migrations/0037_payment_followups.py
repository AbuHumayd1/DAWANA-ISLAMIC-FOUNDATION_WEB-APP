from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('dic', '0036_private_participant_storage')]
    operations = [
        migrations.AddField(model_name='housingjob', name='retry_at',
                            field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name='portalaccount', name='verification_delivery_at',
                            field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name='portalaccount', name='verification_delivery_attempts',
                            field=models.PositiveIntegerField(default=0)),
    ]
