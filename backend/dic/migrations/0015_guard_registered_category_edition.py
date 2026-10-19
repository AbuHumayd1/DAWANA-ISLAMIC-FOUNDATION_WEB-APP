"""Additive integrity repair; never reassign historical categories or identities."""
from django.db import migrations
from django.db.models import F


def validate_existing_sources(apps, schema_editor):
    Enrollment = apps.get_model('dic', 'CampEnrollment')
    if Enrollment.objects.using(schema_editor.connection.alias).exclude(
        source_item__category__edition_id=F('edition_id')
    ).exists():
        raise RuntimeError('Existing enrollment/category edition mismatch requires authorized review before migration 0015. No data was rewritten.')


class Migration(migrations.Migration):
    dependencies = [('dic', '0014_participant_portal_and_ids')]
    operations = [
        migrations.RunPython(validate_existing_sources, migrations.RunPython.noop),
        migrations.RunSQL(
            sql="""
CREATE FUNCTION dic_protect_registered_category() RETURNS trigger AS $$
BEGIN
  IF NEW.edition_id <> OLD.edition_id AND EXISTS (
    SELECT 1 FROM dic_registrationorderitem WHERE category_id = OLD.id
  ) THEN
    RAISE EXCEPTION 'A registered category cannot change edition' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER dic_registered_category_guard BEFORE UPDATE ON dic_registrationcategory
  FOR EACH ROW EXECUTE FUNCTION dic_protect_registered_category();
CREATE OR REPLACE FUNCTION dic_check_enrollment_source() RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'UPDATE' AND (NEW.participant_id <> OLD.participant_id OR NEW.edition_id <> OLD.edition_id OR NEW.participant_number <> OLD.participant_number) THEN
                RAISE EXCEPTION 'Enrollment identity is immutable' USING ERRCODE = '23514';
              END IF;
              PERFORM c.id FROM dic_registrationcategory c
                JOIN dic_registrationorderitem i ON i.category_id = c.id
                WHERE i.id = NEW.source_item_id FOR SHARE OF c;
              IF NOT EXISTS (
                SELECT 1 FROM dic_registrationorderitem i
                JOIN dic_registrationorder o ON o.id = i.order_id
                JOIN dic_registrationcategory c ON c.id = i.category_id
                WHERE i.id = NEW.source_item_id AND i.participant_id = NEW.participant_id
                  AND o.edition_id = NEW.edition_id AND c.edition_id = NEW.edition_id
              ) THEN RAISE EXCEPTION 'Invalid enrollment source' USING ERRCODE = '23514'; END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
""",
            reverse_sql="""
DROP TRIGGER dic_registered_category_guard ON dic_registrationcategory;
DROP FUNCTION dic_protect_registered_category();
CREATE OR REPLACE FUNCTION dic_check_enrollment_source() RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'UPDATE' AND (NEW.participant_id <> OLD.participant_id OR NEW.edition_id <> OLD.edition_id OR NEW.participant_number <> OLD.participant_number) THEN
                RAISE EXCEPTION 'Enrollment identity is immutable' USING ERRCODE = '23514';
              END IF;
              IF NOT EXISTS (
                SELECT 1 FROM dic_registrationorderitem i
                JOIN dic_registrationorder o ON o.id = i.order_id
                JOIN dic_registrationcategory c ON c.id = i.category_id
                WHERE i.id = NEW.source_item_id AND i.participant_id = NEW.participant_id
                  AND o.edition_id = NEW.edition_id AND c.edition_id = NEW.edition_id
              ) THEN RAISE EXCEPTION 'Invalid enrollment source' USING ERRCODE = '23514'; END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
""",
        ),
    ]
