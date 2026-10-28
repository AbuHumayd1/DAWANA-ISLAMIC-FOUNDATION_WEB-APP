"""Proposed, unapplied Phase 2.3 schema. No seeding or permission grants."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('dic', '0025_camp_check_in'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name='HouseScoreTransaction',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('entry_type', models.CharField(choices=[('award', 'Award'), ('deduction', 'Deduction')], max_length=9)),
            ('points', models.PositiveIntegerField()),
            ('activity', models.CharField(max_length=200)),
            ('note', models.TextField(blank=True, max_length=1000)),
            ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ('request_id', models.UUIDField(editable=False)),
            ('edition', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='score_transactions', to='dic.campedition')),
            ('house', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='score_transactions', to='dic.house')),
            ('created_by', models.ForeignKey(editable=False, on_delete=django.db.models.deletion.PROTECT, related_name='dic_score_transactions', to=settings.AUTH_USER_MODEL)),
            ('reverses', models.OneToOneField(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reversal', to='dic.housescoretransaction')),
        ],
        options={
            'default_permissions': (),
            'permissions': [('can_view_dic_scores', 'Can view DIC house scores'), ('can_record_dic_scores', 'Can award and deduct DIC house points'), ('can_correct_dic_scores', 'Can reverse DIC scoring errors')],
            'constraints': [
                models.UniqueConstraint(fields=('edition', 'request_id'), name='dic_score_edition_request_unique'),
                models.CheckConstraint(condition=models.Q(points__gte=1, points__lte=2147483647), name='dic_score_positive_points'),
                models.CheckConstraint(condition=models.Q(entry_type__in=('award', 'deduction')), name='dic_score_entry_type_valid'),
            ],
        },
    )]
