from django.core.validators import RegexValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('dic', '0023_digital_id_cards')]
    operations = [migrations.AddField(
        model_name='house', name='badge_colour',
        field=models.CharField(max_length=7, blank=True,
            validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Use a six-digit hex colour, for example #174a34.')],
            help_text='Committee-approved badge colour. Leave blank until approved.'))]
