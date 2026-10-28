from django.db import migrations, models
import dic.memory_storage


class Migration(migrations.Migration):
    dependencies = [('dic', '0022_housing_guardians_queue')]
    operations = [
        migrations.AddField(model_name='campenrollment', name='portrait', field=models.FileField(blank=True, max_length=200,
            storage=dic.memory_storage.private_memory_storage, validators=[dic.memory_storage.validate_photo],
            help_text='Optional approved participant portrait, stored privately.')),
        migrations.AddField(model_name='digitalidissue', name='verification_digest', field=models.CharField(editable=False, max_length=64, null=True, unique=True)),
        migrations.AddField(model_name='digitalidissue', name='verification_secret', field=models.TextField(blank=True, editable=False)),
    ]
