"""Phase 5 forward schema. Explicit isolated approval required before application."""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('dic', '0027_feedback_welfare')]
    operations = [
        # Existing rows retain the historical three-point interpretation.
        migrations.AddField(model_name='anonymouscamperresponse', name='questionnaire_version', field=models.PositiveSmallIntegerField(default=1), preserve_default=False),
        migrations.AddField(model_name='identifiedfeedback', name='questionnaire_version', field=models.PositiveSmallIntegerField(default=1), preserve_default=False),
        migrations.AlterField(model_name='anonymouscamperresponse', name='questionnaire_version', field=models.PositiveSmallIntegerField(default=2)),
        migrations.AlterField(model_name='identifiedfeedback', name='questionnaire_version', field=models.PositiveSmallIntegerField(default=2)),
        migrations.AddField(model_name='welfarereport', name='affected_participant', field=models.ForeignKey(to='dic.participant', on_delete=django.db.models.deletion.PROTECT, null=True, blank=True)),
        migrations.AddField(model_name='welfarereport', name='urgency', field=models.CharField(max_length=12, choices=[('normal','Normal'),('urgent','Urgent')], default='normal')),
        migrations.AddField(model_name='welfarereport', name='preferred_contact', field=models.CharField(max_length=12, choices=[('none','No preference'),('email','Booking email'),('in_person','In person')], default='none')),
        migrations.AddConstraint(model_name='welfarereport', constraint=models.CheckConstraint(condition=models.Q(urgency__in=('normal','urgent')), name='dic_welfare_valid_urgency')),
        migrations.AddConstraint(model_name='welfarereport', constraint=models.CheckConstraint(condition=models.Q(preferred_contact__in=('none','email','in_person')), name='dic_welfare_valid_contact')),
    ]
