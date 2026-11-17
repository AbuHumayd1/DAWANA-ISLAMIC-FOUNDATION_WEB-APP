"""Remove only exact, unmodified DIC 2026 excluded-game drafts.

Already published meals and administrator-edited records are never touched.
Unconfirmed competition and other programme entries remain drafts pending review.
"""
from datetime import date, time
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
    Audit = apps.get_model("dic", "DICAdminAuditEvent")
    db = schema_editor.connection.alias
    edition = Edition.objects.using(db).filter(
        year=2026, camp_start_date=date(2026, 12, 23),
        camp_end_date=date(2027, 1, 1),
    ).first()
    if edition is None:
        return
    removed = []
    for source_key, (day, description) in EXCLUDED.items():
        # Exact-match guarding preserves modified, published and unrelated rows.
        count, _ = Timetable.objects.using(db).filter(
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
            start_time=time(17, 0),
            end_time=time(18, 30),
            time_label="17:00–18:30",
            display_order=13,
            day_number=2 if day.day == 24 else 3,
            lecturer="",
            meal="",
            location="",
            instructions="",
        ).delete()
        if count:
            removed.append(source_key)
    if removed:
        Audit.objects.using(db).create(
            actor_id=None,
            action="dic2026_excluded_programme_drafts_pruned",
            target_type="CampEdition",
            target_id=str(edition.pk),
            details={"source_keys": removed, "reason": "Owner-excluded Individual Millionaire Challenges",
                     "status": "draft-only exact-match cleanup"},
        )


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
