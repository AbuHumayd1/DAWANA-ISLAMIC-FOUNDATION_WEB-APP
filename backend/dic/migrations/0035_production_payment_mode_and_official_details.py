"""Forward correction only; no fees, bookings, accounts or payment amounts changed."""
from django.db import migrations, models


def correct_official_details(apps, schema_editor):
    Edition = apps.get_model('dic', 'CampEdition')
    editions = Edition.objects.using(schema_editor.connection.alias).filter(year=2026)
    for edition in editions:
        updates = {}
        if edition.name == 'Daarul Islam Camp 2026':
            updates['name'] = 'Darul Islam Camp 2026'
        if edition.venue_name in ('', 'Faisal Omar Memorial School'):
            updates['venue_name'] = 'Fazil Umar Secondary School, Lagos'
        information = dict(edition.general_information or {})
        if not information.get('theme'):
            information['theme'] = 'The Outliers'
            updates['general_information'] = information
        if updates:
            editions.filter(pk=edition.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [('dic', '0034_approved_2026_fees')]
    operations = [
        migrations.AddField(model_name='paymentattempt', name='provider_mode',
            field=models.CharField(max_length=4, choices=[('test', 'Test'), ('live', 'Live')],
                                   default='test', editable=False)),
        migrations.AddField(model_name='foundationdonation', name='provider_mode',
            field=models.CharField(max_length=4, choices=[('test', 'Test'), ('live', 'Live')],
                                   default='test', editable=False)),
        migrations.RunPython(correct_official_details, migrations.RunPython.noop),
    ]
