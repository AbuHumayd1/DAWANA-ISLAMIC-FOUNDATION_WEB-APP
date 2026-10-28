"""Prepared only. Does not depend on or apply dic.0027_feedback_welfare."""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [('dic', '0026_house_score_transaction')]
    operations = [migrations.CreateModel(
        name='ActivityAward',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('kind', models.CharField(choices=[('individual', 'Individual'), ('collective', 'Collective')], max_length=10)),
            ('activity_code', models.CharField(max_length=80)),
            ('activity_date', models.DateField()),
            ('slot', models.CharField(blank=True, max_length=80)),
            ('entitlement_key', models.CharField(max_length=180)),
            ('exclusion_key', models.CharField(blank=True, max_length=180)),
            ('cap_bucket', models.CharField(blank=True, max_length=12)),
            ('evidence', models.JSONField(default=dict)),
            ('submission_fingerprint', models.CharField(max_length=64)),
            ('verified_at', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ('edition', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='dic.campedition')),
            ('house', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='dic.house')),
            ('participant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='dic.participant')),
            ('allocation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='dic.houseallocation')),
            ('ledger_entry', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='activity_award', to='dic.housescoretransaction')),
        ],
        options={
            'default_permissions': (), 'ordering': ('-activity_date', '-pk'),
            'indexes': [models.Index(fields=['edition', 'participant', 'activity_date'], name='dic_activity_person_day')],
            'constraints': [
                models.CheckConstraint(condition=(models.Q(kind='individual', participant__isnull=False, allocation__isnull=False) | models.Q(kind='collective', participant__isnull=True, allocation__isnull=True)), name='dic_activity_kind_identity'),
                models.CheckConstraint(condition=models.Q(cap_bucket__in=('', 'service', 'character')), name='dic_activity_cap_bucket'),
                models.UniqueConstraint(fields=('edition', 'participant', 'entitlement_key'), condition=models.Q(kind='individual'), name='dic_activity_individual_unique'),
                models.UniqueConstraint(fields=('edition', 'house', 'entitlement_key'), condition=models.Q(kind='collective'), name='dic_activity_collective_unique'),
                models.UniqueConstraint(fields=('edition', 'participant', 'exclusion_key'), condition=~models.Q(exclusion_key=''), name='dic_activity_exclusion_unique'),
            ],
        },
    )]
