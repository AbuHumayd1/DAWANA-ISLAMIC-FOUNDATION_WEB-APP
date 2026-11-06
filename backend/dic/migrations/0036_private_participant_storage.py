"""Storage routing only; does not copy, move or delete existing objects."""
from django.db import migrations, models
import dic.memory_storage


class Migration(migrations.Migration):
    dependencies = [('dic', '0035_production_payment_mode_and_official_details')]
    operations = [migrations.AlterField(model_name='campenrollment', name='portrait',
        field=models.FileField(blank=True, max_length=200,
            storage=dic.memory_storage.PrivateParticipantStorage(),
            validators=[dic.memory_storage.validate_photo],
            help_text='Optional approved participant portrait, stored privately.'))]
