"""Published camper content, selected by authoritative camper and Lagos date."""
from datetime import date
from zoneinfo import ZoneInfo
from django.utils import timezone
from django.db.models import Q
LAGOS=ZoneInfo('Africa/Lagos')


def camper_age(person, edition):
    birth=person.date_of_birth
    if birth:
        day=edition.camp_start_date
        return day.year-birth.year-((day.month,day.day)<(birth.month,birth.day))
    return 18 if person.age_declaration == 'adult' else None


def audience_rows(query, person, edition):
    age=camper_age(person,edition)
    groups=['all']
    if age is not None:
        if 5<=age<=9: groups.append('talim')
        if 10<=age<=15: groups.append('tahdheeb')
        if age>=16: groups.append('dawah')
        if age>=18: groups.append('adults')
    return query.filter(audience__in=groups).filter(Q(gender='all')|Q(gender=person.sex.lower()))


def overlap(left,right):
    if left.gender != 'all' and right.gender != 'all' and left.gender != right.gender: return False
    if left.audience != 'all' and right.audience != 'all' and left.audience != right.audience:
        if {left.audience,right.audience}!={'dawah','adults'}: return False
    return left.start_time < right.end_time and right.start_time < left.end_time
