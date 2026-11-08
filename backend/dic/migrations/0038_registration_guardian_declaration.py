from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('dic', '0037_payment_followups')]
    operations = [migrations.AddField(model_name='guardianrelationship', name='registration_declared',
                                     field=models.BooleanField(default=False))]
