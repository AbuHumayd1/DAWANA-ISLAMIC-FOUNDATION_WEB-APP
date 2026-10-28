"""Existing Operations/session and booking authentication, with scoped projections."""
from django.db import connection, transaction
from django.db.models import Count, Sum
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from dic_scoring.models import ActivityAward
from .activity_scoring import activity_storage_ready, eligible_members, record_activity
from .models import HouseAllocation, HouseScoreTransaction, RegistrationOrderItem, CampEdition
from .operations_api import OperationsBaseView
from .participant_api import PortalView, authorized_grant, scoped_orders
from .scoring_api import write_edition
from .scoring_catalogue import catalogue_options
from .scoring_services import require_scoring_staff, scoring_houses, combined_leaderboard


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise ValidationError('Only the documented activity fields are accepted.')
        return super().to_internal_value(data)


class ExemptionInput(StrictInput):
    participant = serializers.UUIDField()
    reason = serializers.CharField(max_length=300)


class AssessmentInput(StrictInput):
    house = serializers.IntegerField(min_value=1)
    marks = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)


class ActivityInput(StrictInput):
    activity = serializers.CharField(max_length=80)
    date = serializers.DateField()
    slot = serializers.RegexField(r'^[a-z0-9][a-z0-9_-]{0,79}$', required=False, allow_blank=True, default='')
    participant = serializers.UUIDField(required=False)
    house = serializers.IntegerField(min_value=1, required=False)
    attendees = serializers.ListField(child=serializers.UUIDField(), max_length=500, default=list)
    exemptions = ExemptionInput(many=True, max_length=500, default=list)
    results = AssessmentInput(many=True, max_length=100, default=list)
    reading_target = serializers.RegexField(r'^[a-z0-9][a-z0-9_-]{0,79}$', required=False, allow_blank=True, default='')
    verified = serializers.BooleanField()
    note = serializers.CharField(max_length=600, allow_blank=True, default='')
    request_id = serializers.UUIDField()


class ActivityScoringView(OperationsBaseView):
    def get(self, request):
        require_scoring_staff(request.user, 'can_record_dic_scores')
        edition = write_edition(request)
        options = catalogue_options()
        if edition.year != 2026:
            options.update(ready=False, message='The fixed activity catalogue is approved for DIC 2026 only. Direct house scoring remains available.')
        options.update(storage_ready=activity_storage_ready(), edition=edition.pk,
            start_date=edition.camp_start_date, end_date=edition.camp_end_date,
            members=[dict(id=str(row.participant_id), name=row.participant.full_name,
                house=row.house_id, house_name=row.house.name) for row in eligible_members(edition)],
            houses=list(scoring_houses(edition).filter(status='active').values('id', 'name')))
        return Response(options)

    def post(self, request):
        require_scoring_staff(request.user, 'can_record_dic_scores')
        edition = write_edition(request)
        data = ActivityInput(data=request.data)
        data.is_valid(raise_exception=True)
        award, created = record_activity(edition, request.user, data.validated_data)
        return Response(dict(id=award.pk, ledger_id=award.ledger_entry_id,
            points=award.ledger_entry.points, created=created), status=201 if created else 200)


def ranked_people(rows):
    rows.sort(key=lambda row: (-row['points'], row['name'].casefold(), row['_key']))
    previous, rank = None, 0
    for index, row in enumerate(rows, 1):
        row.pop('_key')
        if row['points'] != previous:
            rank = index
        row['rank'] = rank
        previous = row['points']
    return rows


def camper_scores(item, page):
    edition, pid = item.order.edition, item.participant_id
    from .tutor_registration import is_tutor
    if is_tutor(pid, edition.pk):
        return dict(ready=False, competitive=False, message='Tutors do not participate in house competitions.', standings=[], history=[], count=0, total=None, page=page, page_size=25, house=None, house_leaderboard=[])
    tables = connection.introspection.table_names()
    ledger_ready = HouseScoreTransaction._meta.db_table in tables
    ready = ActivityAward._meta.db_table in tables and ledger_ready
    houses = list(scoring_houses(edition))
    standings = combined_leaderboard(houses, HouseScoreTransaction.objects.filter(edition=edition)) if ledger_ready else []
    result = dict(ready=ready, standings_ready=ledger_ready, standings=standings,
        message='' if ready else 'Activity scoring is awaiting its approved database setup.',
        total=None, history=[], count=0, page=page, page_size=25, house=None, house_leaderboard=[])
    if not ready:
        return result
    own = ActivityAward.objects.filter(edition=edition, participant_id=pid, kind='individual')
    result['total'] = own.filter(ledger_entry__reversal__isnull=True).aggregate(total=Sum('ledger_entry__points'))['total'] or 0
    result['count'] = own.count()
    for award in own.select_related('house', 'ledger_entry__reversal').order_by('-activity_date', '-pk')[(page-1)*25:page*25]:
        reversed_entry = getattr(award.ledger_entry, 'reversal', None)
        result['history'].append(dict(id=award.pk, activity=award.ledger_entry.activity,
            date=award.activity_date, slot=award.slot, house=award.house.name,
            points=award.ledger_entry.points, reversed=bool(reversed_entry),
            net=0 if reversed_entry else award.ledger_entry.points))
    current = list(HouseAllocation.objects.filter(edition=edition, participant_id=pid,
        status='allocated').select_related('house')[:2])
    if (len(current) != 1 or current[0].house.edition_id != edition.pk
            or current[0].house.purpose != 'participants' or current[0].house.status != 'active'):
        return result
    house = current[0].house
    result['house'] = house.name
    members = list(HouseAllocation.objects.filter(edition=edition, house=house, status='allocated').select_related('participant'))
    member_ids = [row.participant_id for row in members]
    counts = dict(HouseAllocation.objects.filter(edition=edition, status='allocated', participant_id__in=member_ids)
        .values('participant_id').annotate(n=Count('pk')).values_list('participant_id', 'n'))
    totals = dict(ActivityAward.objects.filter(edition=edition, house=house, kind='individual',
        participant_id__in=member_ids, ledger_entry__reversal__isnull=True)
        .values('participant_id').annotate(points=Sum('ledger_entry__points')).values_list('participant_id', 'points'))
    people = []
    for member in members:
        if counts[member.participant_id] != 1:
            continue
        names = member.participant.full_name.split()
        label = names[0] + (f' {names[-1][0]}.' if len(names) > 1 else '') if names else 'Camper'
        people.append(dict(name=label, points=totals.get(member.participant_id, 0),
            own=member.participant_id == pid, _key=str(member.participant_id)))
    result['house_leaderboard'] = ranked_people(people)
    return result


class CamperScoringView(PortalView):
    @transaction.atomic
    def get(self, request):
        grant = authorized_grant(request)
        try:
            item_id, page = int(request.query_params.get('item', '')), int(request.query_params.get('page', '1'))
            if item_id < 1 or page < 1:
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError('Choose an authorised camper and valid history page.')
        item = RegistrationOrderItem.objects.filter(pk=item_id,
            order_id__in=[row.pk for row in scoped_orders(grant)]).select_related('order__edition').first()
        if not item:
            raise NotFound('Participant record not found.')
        # Share the existing transfer/scoring mutex while projecting house scope.
        CampEdition.objects.select_for_update().get(pk=item.order.edition_id)
        return Response(camper_scores(item, page))
