"""Remove only exact, unmodified DIC 2026 excluded-game drafts.

Already published meals and administrator-edited records are never touched.
Unconfirmed competition and other programme entries remain drafts pending review.
"""
from datetime import date
from django.db import migrations

EXCLUDED = {
    "dic2026:activities:2:13": (
        date(2026, 12, 24),
        "Individual Millionaire- Challenge: Ta’lim & Tahdheeb",
    ),
    "dic2026:activities:3:13": (
        date(2026, 12, 25),
        "Individual Millionaire- Challenge: Da’wah Youth & Adults",
    ),
}


def remove_unmodified_excluded_drafts(apps, schema_editor):
    Edition = apps.get_model("dic", "CampEdition")
    Timetable = apps.get_model("dic", "TimetableEntry")
    db = schema_editor.connection.alias
    edition = Edition.objects.using(db).filter(
        year=2026, camp_start_date=date(2026, 12, 23),
        camp_end_date=date(2027, 1, 1),
    ).first()
    if edition is None:
        return
    for source_key, (day, description) in EXCLUDED.items():
        # Exact-match guarding preserves modified, published and unrelated rows.
        Timetable.objects.using(db).filter(
            edition_id=edition.pk,
            timetable_type="activities",
            source_key=source_key,
            date=day,
            description=description,
            title="",
            status="draft",
            certainty="unspecified",
            gender="all",
            audience="all",
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("dic", "0042_integrated_camp_2026"),
    ]
    operations = [
        migrations.RunPython(
            remove_unmodified_excluded_drafts,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
