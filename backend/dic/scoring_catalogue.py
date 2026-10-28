"""DIC 2026 CP-3C.1 fixed approved scoring catalogue. No runtime configuration."""
from dataclasses import asdict, dataclass
from decimal import Decimal
from rest_framework.exceptions import ValidationError

PRAYERS = ('fajr', 'dhuhr', 'asr', 'maghrib', 'isha')
RAWATIB = ('before_fajr', 'before_dhuhr', 'after_dhuhr', 'after_maghrib', 'after_isha')
POLICY_PENDING = 'The fixed approved scoring catalogue failed validation. Activity awards are unavailable.'


@dataclass(frozen=True)
class Activity:
    code: str
    name: str
    kind: str
    category: str
    points: int | None = None
    frequency: str = 'daily'
    mode: str = 'verified'
    threshold: str | None = None
    cap_bucket: str = ''
    exclusion_group: str = ''


INDIVIDUAL_ACTIVITIES = tuple(Activity(code, name, 'individual', category, points,
    frequency, mode, cap_bucket=cap, exclusion_group=exclusion) for code, name, points, frequency, category, cap, exclusion, mode in (
    ('SAL01', 'Arrival before adhān', 3, 'prayer', 'Ṣalāh and Worship', '', 'punctuality', 'verified'),
    ('SAL02', 'Arrival after adhān but before iqāmah', 2, 'prayer', 'Ṣalāh and Worship', '', 'punctuality', 'verified'),
    ('SAL03', 'Congregational ṣalāh', 2, 'prayer', 'Ṣalāh and Worship', '', '', 'verified'),
    ('SAL04', 'Sunnah Rawātib', 2, 'rawatib', 'Ṣalāh and Worship', '', '', 'verified'),
    ('SAL05', 'Ṣalāt al-Ḍuḥā', 3, 'daily', 'Ṣalāh and Worship', '', '', 'verified'),
    ('SAL06', 'Tahajjud', 5, 'daily', 'Ṣalāh and Worship', '', '', 'verified'),
    ('SAL07', 'Witr', 3, 'daily', 'Ṣalāh and Worship', '', '', 'verified'),
    ('ADH01', 'Morning Adhkār', 3, 'daily', 'Adhkār and Duʿāʾ', '', '', 'verified'),
    ('ADH02', 'Evening Adhkār', 3, 'daily', 'Adhkār and Duʿāʾ', '', '', 'verified'),
    ('ADH03', 'Post-ṣalāh Adhkār', 2, 'prayer', 'Adhkār and Duʿāʾ', '', '', 'verified'),
    ('ADH04', 'Before-sleep Adhkār', 2, 'daily', 'Adhkār and Duʿāʾ', '', '', 'verified'),
    ('ADH05', 'Memorising a new Duʿāʾ', 5, 'target', 'Adhkār and Duʿāʾ', '', '', 'verified'),
    ('QUR01', "Daily Qur'ān recitation", 3, 'daily', "Qur'ān and Islamic Learning", '', '', 'verified'),
    ('QUR02', 'Memorising new āyāt', 5, 'target', "Qur'ān and Islamic Learning", '', '', 'verified'),
    ('QUR03', 'Memorising a Ḥadīth', 5, 'target', "Qur'ān and Islamic Learning", '', '', 'verified'),
    ('QUR04', 'Arriving early for lessons', 2, 'session', "Qur'ān and Islamic Learning", '', '', 'verified'),
    ('QUR05', 'Completing Islamic reading tasks', 5, 'target', "Qur'ān and Islamic Learning", '', '', 'verified'),
    ('SRV01', 'Sweeping the masjid', 5, 'target', 'Service and Cleanliness', 'service', 'service_task', 'verified'),
    ('SRV02', 'Mopping the masjid', 5, 'target', 'Service and Cleanliness', 'service', 'service_task', 'verified'),
    ('SRV03', 'Cleaning the ablution area', 5, 'target', 'Service and Cleanliness', 'service', 'service_task', 'verified'),
    ('SRV04', 'Arranging prayer mats', 3, 'target', 'Service and Cleanliness', 'service', 'service_task', 'verified'),
    ('SRV05', 'Picking up litter', 2, 'target', 'Service and Cleanliness', 'service', 'service_task', 'verified'),
    ('SRV06', 'Cleaning the camp environment', 5, 'target', 'Service and Cleanliness', 'service', 'service_task', 'verified'),
    ('SRV07', 'Cleaning the dining area', 3, 'target', 'Service and Cleanliness', 'service', 'service_task', 'verified'),
    ('SRV08', 'Cleaning the dormitory', 3, 'target', 'Service and Cleanliness', 'service', 'service_task', 'verified'),
    ('CHR01', 'Helping younger campers', 3, 'target', 'Character and Kindness', 'character', 'character_incident', 'verified'),
    ('CHR02', 'Assisting a sick camper', 5, 'target', 'Character and Kindness', 'character', 'character_incident', 'verified'),
    ('CHR03', 'Returning lost property', 5, 'target', 'Character and Kindness', 'character', 'character_incident', 'verified'),
    ('CHR04', 'Demonstrating exceptional honesty', 5, 'target', 'Character and Kindness', 'character', 'character_incident', 'verified'),
    ('CHR05', 'Helping a struggling camper', 3, 'target', 'Character and Kindness', 'character', 'character_incident', 'verified'),
    ('CHR06', 'Volunteering for useful tasks', 3, 'target', 'Character and Kindness', 'character', 'character_incident', 'verified'),
    ('CHR07', 'Demonstrating outstanding manners', 5, 'target', 'Character and Kindness', 'character', 'character_incident', 'verified'),
    ('MIL01', 'Tahajjud consistency', 10, 'once', 'Special Milestones', '', '', 'milestone'),
    ('MIL02', 'Adhkār consistency', 10, 'once', 'Special Milestones', '', '', 'milestone'),
    ('MIL03', "Qur'ān consistency", 10, 'once', 'Special Milestones', '', '', 'milestone'),
    ('MIL04', 'Duʿāʾ memorisation milestone', 10, 'once', 'Special Milestones', '', '', 'milestone'),
    ('MIL05', 'Reading challenge milestone', 10, 'once', 'Special Milestones', '', '', 'milestone'),
    ('MIL06', 'Community service milestone', 10, 'once', 'Special Milestones', '', '', 'milestone'),
))
COLLECTIVE_ACTIVITIES = tuple(Activity(code, name, 'collective', category, points,
    frequency, mode, threshold) for code, name, points, frequency, category, mode, threshold in (
    ('HSP01', 'Tahajjud participation', 15, 'daily', 'Spiritual Participation', 'participation', '70'),
    ('HSP02', 'Morning Adhkār participation', 10, 'daily', 'Spiritual Participation', 'participation', '80'),
    ('HSP03', 'Evening Adhkār participation', 10, 'daily', 'Spiritual Participation', 'participation', '80'),
    ('HSP04', "Qur'ān recitation participation", 10, 'daily', 'Spiritual Participation', 'participation', '80'),
    ('HSP05', 'Prayer punctuality challenge', 15, 'daily', 'Spiritual Participation', 'prayer_target', '80'),
    ('HSP06', 'House Duʿāʾ memorisation', 15, 'target', 'Spiritual Participation', 'participation', '70'),
    ('HSP07', 'Class and Camp Lectures Attendance', 15, 'session', 'Spiritual Participation', 'participation', '80'),
    ('HCL01', 'Cleanest dormitory', 15, 'daily', 'Cleanliness and Service', 'inspection', None),
    ('HCL02', 'Best-maintained house surroundings', 10, 'daily', 'Cleanliness and Service', 'inspection', None),
    ('HCL03', 'Collective masjid sanitation', 15, 'target', 'Cleanliness and Service', 'verified', None),
    ('HCL04', 'Cleanest assigned dining area', 10, 'daily', 'Cleanliness and Service', 'inspection', None),
    ('HCL05', 'House environmental clean-up', 15, 'target', 'Cleanliness and Service', 'verified', None),
    ('HCL06', 'Best house organisation and tidiness', 10, 'daily', 'Cleanliness and Service', 'inspection', None),
    ('HKN01', "Qur'ān memorisation challenge", 20, 'target', 'Islamic Knowledge Competitions', 'competition', None),
    ('HKN02', 'Ḥadīth memorisation challenge', 20, 'target', 'Islamic Knowledge Competitions', 'competition', None),
    ('HKN03', 'Sīrah challenge', 20, 'target', 'Islamic Knowledge Competitions', 'competition', None),
    ('HKN04', 'Islamic presentation challenge', 15, 'target', 'Islamic Knowledge Competitions', 'competition', None),
))


def catalogue():
    return INDIVIDUAL_ACTIVITIES + COLLECTIVE_ACTIVITIES


def policy_ready():
    rows = catalogue()
    return (len(INDIVIDUAL_ACTIVITIES) == 38 and len(COLLECTIVE_ACTIVITIES) == 17
        and len({row.code for row in rows}) == 55 and all(configured(row) for row in rows))


def configured(row):
    try:
        points_ok = type(row.points) is int and 1 <= row.points <= 2147483647
        threshold_ok = row.mode not in ('participation', 'prayer_target') or (row.threshold is not None and Decimal(0) < Decimal(row.threshold) <= Decimal(100))
        return points_ok and threshold_ok and row.frequency in ('daily', 'prayer', 'rawatib', 'target', 'session', 'once') and row.cap_bucket in ('', 'service', 'character')
    except (ValueError, ArithmeticError):
        return False


def activity_for(code):
    if not policy_ready():
        raise ValidationError(POLICY_PENDING)
    row = next((row for row in catalogue() if row.code == code), None)
    if row is None:
        raise ValidationError('Choose an approved scoring activity.')
    return row


def catalogue_options():
    return dict(ready=policy_ready(), message='' if policy_ready() else POLICY_PENDING,
        individual=[asdict(row) for row in INDIVIDUAL_ACTIVITIES],
        collective=[asdict(row) for row in COLLECTIVE_ACTIVITIES], prayers=PRAYERS, rawatib=RAWATIB)
