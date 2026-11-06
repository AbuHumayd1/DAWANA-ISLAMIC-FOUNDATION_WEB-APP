"""Approved payment defaults only. Never rewrite registration/payment snapshots."""
from datetime import date
from decimal import Decimal

from django.db import migrations, models


FEES = (
    ('Pre-Primary', 'pre_primary', 0, 5, '4000', '5000'),
    ('Primary', 'primary', 6, 10, '10000', '12000'),
    ('Secondary', 'secondary', 11, 16, '12000', '15000'),
    ('Undergraduates', 'undergraduate', 17, 24, '15000', '17000'),
    ('Graduates & Adults', 'graduate_adult', None, None, '18000', '18500'),
)


def seed_approved_fees(apps, schema_editor):
    alias = schema_editor.connection.alias
    Edition = apps.get_model('dic', 'CampEdition')
    Category = apps.get_model('dic', 'RegistrationCategory')
    edition, _ = Edition.objects.using(alias).get_or_create(
        year=2026,
        defaults=dict(name='Daarul Islam Camp 2026',
                      camp_start_date=date(2026, 12, 23), camp_end_date=date(2027, 1, 1),
                      venue_name='Faisal Omar Memorial School', registration_status='draft',
                      is_active=False),
    )
    for name, kind, minimum, maximum, early, regular in FEES:
        category, created = Category.objects.using(alias).get_or_create(
            edition_id=edition.pk, name=name,
            defaults=dict(payment_kind=kind, minimum_age=minimum, maximum_age=maximum,
                          early_bird_fee_ngn=Decimal(early), fee_ngn=Decimal(regular)),
        )
        if not created:
            # An existing value, including zero or an inactive flag, is an override.
            # Never infer that an administrator's price is a placeholder.
            updates = dict(payment_kind=kind, minimum_age=minimum, maximum_age=maximum)
            if category.fee_ngn is None:
                updates['fee_ngn'] = Decimal(regular)
            if category.early_bird_fee_ngn is None:
                updates['early_bird_fee_ngn'] = Decimal(early)
            Category.objects.using(alias).filter(pk=category.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [('dic', '0033_launch_completion')]
    operations = [
        migrations.AddField(
            model_name='registrationcategory', name='payment_kind',
            field=models.CharField(blank=True, default='', max_length=20,
                choices=[('pre_primary', 'Pre-Primary'), ('primary', 'Primary'),
                         ('secondary', 'Secondary'), ('undergraduate', 'Undergraduates'),
                         ('graduate_adult', 'Graduates & Adults')],
                help_text='Payment eligibility only; does not change housing, safeguarding or academic allocation.'),
        ),
        # Reversal intentionally retains configured fees and historical records.
        migrations.RunPython(seed_approved_fees, migrations.RunPython.noop),
    ]
