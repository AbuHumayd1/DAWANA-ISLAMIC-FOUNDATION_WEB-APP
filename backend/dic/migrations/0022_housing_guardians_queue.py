import uuid
from datetime import date
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def initialize_policy(apps, schema_editor):
    alias = schema_editor.connection.alias
    apps.get_model('dic', 'CampEdition').objects.using(alias).filter(year=2026, housing_age_reference_date__isnull=True).update(housing_age_reference_date=date(2026, 12, 23))
    apps.get_model('dic', 'House').objects.using(alias).filter(status='reserve').update(reserve_designation=True)
    # Existing approval records remain intact. The extended configuration
    # fingerprint naturally requires a fresh inventory/policy approval.


class Migration(migrations.Migration):
    dependencies = [('dic', '0021_promovideo_campflyer'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name='campedition', name='housing_age_reference_date', field=models.DateField(blank=True, null=True, help_text='Housing age reference date; DIC 2026 uses 23 December 2026.')),
        migrations.AddField(model_name='house', name='reserve_designation', field=models.BooleanField(default=False, editable=False)),
        migrations.RunPython(initialize_policy, migrations.RunPython.noop),
        migrations.AddConstraint(model_name='house', constraint=models.CheckConstraint(condition=(~models.Q(status='active') | models.Q(reserve_designation=False)) & (~models.Q(status='reserve') | models.Q(reserve_designation=True)), name='dic_reserve_designation_safe')),
        migrations.CreateModel(
            name='GuardianRelationship',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Awaiting approval'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('revoked', 'Revoked')], default='pending', max_length=10)),
                ('reason', models.TextField()),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('edition', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='dic.campedition')),
                ('child', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='housing_guardians', to='dic.participant')),
                ('guardian', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='housing_dependents', to='dic.participant')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'permissions': [('can_approve_housing_guardians', 'Can approve or revoke housing guardians')],
                'constraints': [
                    models.UniqueConstraint(fields=['edition', 'child'], condition=models.Q(status__in=['pending', 'approved']), name='dic_one_current_guardian'),
                    models.CheckConstraint(condition=~models.Q(child=models.F('guardian')), name='dic_guardian_not_child'),
                    models.CheckConstraint(condition=models.Q(status__in=['pending', 'approved', 'rejected', 'revoked']), name='dic_guardian_status_valid'),
                    models.CheckConstraint(condition=models.Q(status='pending') | (models.Q(reviewed_by__isnull=False) & models.Q(reviewed_at__isnull=False)), name='dic_guardian_review_required'),
                    models.CheckConstraint(condition=~models.Q(status='approved') | (models.Q(approved_by__isnull=False) & models.Q(approved_at__isnull=False)), name='dic_guardian_approval_required'),
                ],
            },
        ),
        migrations.CreateModel(
            name='HousingJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('state', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('held', 'Held for supervisor review'), ('failed', 'Failed; explicit retry required')], default='pending', max_length=10)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('reason', models.TextField(blank=True)),
                ('claimed_at', models.DateTimeField(blank=True, null=True)),
                ('claim_token', models.UUIDField(default=uuid.uuid4, editable=False)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('edition', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='dic.campedition')),
                ('participant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='dic.participant')),
            ],
            options={
                'permissions': [('can_process_housing_queue', 'Can process and retry housing jobs')],
                'constraints': [
                    models.UniqueConstraint(fields=['edition', 'participant'], name='dic_housing_job_unique'),
                    models.CheckConstraint(condition=models.Q(state__in=['pending', 'processing', 'completed', 'held', 'failed']), name='dic_housing_job_state_valid'),
                ],
                'indexes': [models.Index(fields=['state', 'created_at'], name='dic_housing_queue_idx')],
            },
        ),
    ]
