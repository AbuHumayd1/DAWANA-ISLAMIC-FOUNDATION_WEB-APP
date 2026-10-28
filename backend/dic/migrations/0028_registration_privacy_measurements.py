"""Prepared only. Phase 2 precedes unchanged Phase 5 migration 0027."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('dic', '0026_house_score_transaction')]
    run_before = [('dic', '0027_feedback_welfare')]
    operations = [
        migrations.AlterField(model_name='participant', name='date_of_birth', field=models.DateField(null=True, blank=True)),
        migrations.AlterField(model_name='participant', name='height_cm', field=models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)),
        migrations.AlterField(model_name='participant', name='weight_kg', field=models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)),
        migrations.AddField(model_name='participant', name='age_declaration', field=models.CharField(max_length=5, default='exact', choices=[('exact', 'Exact date of birth'), ('minor', 'Minor (under 18)'), ('adult', 'Adult (18+)')])),
        migrations.AddField(model_name='participant', name='adult_declared_on', field=models.DateField(null=True, blank=True, editable=False)),
        migrations.AddConstraint(model_name='participant', constraint=models.CheckConstraint(condition=models.Q(age_declaration__in=['exact', 'minor', 'adult']), name='dic_participant_age_declaration')),
        migrations.AddConstraint(model_name='participant', constraint=models.CheckConstraint(condition=(models.Q(date_of_birth__isnull=False, adult_declared_on__isnull=True) | models.Q(date_of_birth__isnull=True, age_declaration='adult', adult_declared_on__isnull=False)), name='dic_participant_age_evidence')),
    ]
