"""Minimal booking-scoped arrival/housing projection; no writes or ID dependency."""
import re
from .models import HouseAllocation, CampCheckIn


def camper_operations_summary(participant_id, edition):
    from .tutor_registration import is_tutor
    if is_tutor(participant_id, edition.pk):
        return dict(registration_basis='tutor', competitive=False,
            checked_in=CampCheckIn.objects.filter(participant_id=participant_id, edition=edition).exists())
    rows=list(HouseAllocation.objects.filter(participant_id=participant_id,edition=edition,
        status='allocated',house__edition=edition,house__status='active',
        house__purpose='participants').select_related('house')[:2])
    house=rows[0].house if len(rows)==1 else None
    colour=house.badge_colour if house and re.fullmatch(r'#[0-9a-fA-F]{6}',house.badge_colour or '') else None
    return dict(house_assignment=dict(name=house.name,colour=colour) if house else None,
        checked_in=CampCheckIn.objects.filter(participant_id=participant_id,edition=edition).exists())
