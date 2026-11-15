"""Real endpoint lifecycle regression fixtures; never use production settings."""
import uuid
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from . import test_operations_portal as portal_fixtures
from .models import (CampEdition, RegistrationCategory, PaymentAttempt,
    CampCheckIn, DigitalIDIssue, DICAdminAuditEvent, House, HouseAllocation)
from .participant_services import ensure_enrollment
from .identity_cards import command
from .testing_settlement import complete_settlement_fixture
from .registration_scope import lifecycle_orders


class LifecycleFixture:
    def setUp(self):
        today = timezone.localdate()
        self.edition = CampEdition.objects.create(name='Lifecycle acceptance', year=2094,
            camp_start_date=today+timedelta(days=30), camp_end_date=today+timedelta(days=36),
            housing_age_reference_date=today, is_active=True)
        self.category = RegistrationCategory.objects.create(edition=self.edition, name='Camper', fee_ngn=1000)
        self.actor = get_user_model().objects.create_superuser('lifecycle-owner', 'owner@example.test', 'synthetic')
        self.client.force_login(self.actor)
        self.active = self.make_order(('Active Camper', 'Active Sibling'), paid=True)
        self.deleted_unpaid = self.make_order(('Deleted Unpaid', 'Deleted Sibling'), paid=False)
        self.archived = self.make_order(('Archived Camper',), paid=False)
        self.deleted_paid = self.make_order(('Historical Paid', 'Historical Paid Sibling'), paid=True)
        self.enrollments = {}
        for order in (self.active, self.deleted_unpaid, self.archived, self.deleted_paid):
            for item in order.items.all():
                self.enrollments[item.participant_id] = ensure_enrollment(item.pk)
        self.person = self.active.items.first().participant
        self.historical_person = self.deleted_paid.items.first().participant
        self.current_id = command(self.enrollments[self.person.pk], 'issue', self.actor, 'Synthetic ID')
        self.historical_id = command(self.enrollments[self.historical_person.pk], 'issue', self.actor, 'Synthetic historical ID')
        self.arrival = CampCheckIn.objects.create(edition=self.edition, participant=self.person, checked_in_by=self.actor)
        self.historical_arrival = CampCheckIn.objects.create(edition=self.edition, participant=self.historical_person, checked_in_by=self.actor)
        self.house = House.objects.create(edition=self.edition, name='Acceptance House', gender='male', capacity=20)
        self.allocation = HouseAllocation.objects.create(edition=self.edition, participant=self.person,
            house=self.house, status='allocated', allocated_by=self.actor)
        self.change(self.deleted_unpaid, 'delete')
        self.change(self.deleted_paid, 'delete')
        self.change(self.archived, 'archive')

    def make_order(self, names, *, paid):
        order = portal_fixtures.DICOperationsPortalTests.make_order(self, names, paid=False)
        if paid:
            order.status = 'confirmed'; order.payment_status = 'paid'
            order.save(update_fields=['status', 'payment_status'])
            attempt = PaymentAttempt.objects.create(order=order, reference='lifecycle-'+uuid.uuid4().hex,
                amount_kobo=len(names)*100000, status='successful', currency='NGN')
            complete_settlement_fixture(order, attempt)
        else:
            PaymentAttempt.objects.create(order=order, reference='unpaid-'+uuid.uuid4().hex,
                amount_kobo=len(names)*100000, status='pending', currency='NGN')
        return order

    def change(self, order, action):
        routes={'delete':'operations-registration-delete', 'restore':'operations-registration-restore-deleted',
            'archive':'operations-registration-archive-test', 'unarchive':'operations-registration-unarchive'}
        response = self.client.post(reverse('dic:'+routes[action], args=[order.public_id]),
            {'confirmation': str(order.public_id), 'reason':'Synthetic lifecycle acceptance'}, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)

    def get(self, name, **query):
        response = self.client.get(reverse('dic:'+name), {'edition': self.edition.pk, **query})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def assert_active(self, count):
        checkin = self.get('operations-check-in')
        self.assertEqual(checkin['totals']['registered'], count)
        self.assertEqual(checkin['count'], count)
        self.assertEqual(self.get('operations-enrollments')['count'], count)
        self.assertEqual(self.get('operations-participants')['count'], count)
        self.assertEqual(self.get('operations-dashboard')['metrics']['participants'], count)
        return checkin


class OperationsLifecycleTests(LifecycleFixture, TestCase):
    def test_complete_lifecycles_update_every_active_directory_but_keep_receipts(self):
        self.assert_active(2)
        for hidden in (self.deleted_unpaid, self.deleted_paid):
            self.change(hidden, 'restore'); self.assert_active(4)
            self.change(hidden, 'archive'); self.assert_active(2)
            self.change(hidden, 'unarchive'); self.assert_active(4)
            self.change(hidden, 'delete'); self.assert_active(2)
            self.assertEqual(self.get('operations-finance')['summary']['net_position_kobo'], 400000)
        self.change(self.archived, 'unarchive'); self.assert_active(3)
        self.change(self.archived, 'archive'); self.assert_active(2)

    def test_active_checkin_and_search_exclude_hidden_registrations_and_preserve_arrivals(self):
        data = self.assert_active(2)
        self.assertEqual(data['totals'], dict(registered=2, checked_in=1, not_yet_arrived=1, needs_attention=0))
        self.assertEqual(self.get('operations-check-in', search='Deleted')['count'], 0)
        self.assertEqual(self.get('operations-check-in', search=str(self.deleted_paid.public_id))['count'], 0)
        history = self.get('operations-check-in', view='history')
        self.assertEqual(history['totals']['checked_in'], 2)
        self.assertEqual(history['count'], 7)
        for order in (self.deleted_unpaid, self.deleted_paid, self.archived):
            for item in order.items.all():
                result = self.client.post(reverse('dic:operations-check-in')+'?edition='+str(self.edition.pk),
                    {'participant_id':str(item.participant_id)}, content_type='application/json')
                self.assertEqual(result.status_code, 400, result.content)
        self.assertEqual(CampCheckIn.objects.count(), 2)
        self.assertEqual(CampCheckIn.objects.get(pk=self.arrival.pk).checked_in_at, self.arrival.checked_in_at)
        self.assertEqual(CampCheckIn.objects.get(pk=self.historical_arrival.pk).checked_in_by_id, self.actor.pk)

    def test_id_candidates_and_commands_obey_active_scope_without_revoking_issued_records(self):
        data = self.get('operations-enrollments')
        self.assertEqual(len(data['registration_candidates']), 2)
        self.assertEqual(self.get('operations-enrollments', q='Deleted')['count'], 0)
        history = self.get('operations-enrollments', view='history')
        self.assertEqual(history['count'], 7)
        self.assertEqual(history['registration_candidates'], [])
        self.assertEqual(sum(len(row.get('issue_history', [])) for row in history['results']),2)
        before = list(DigitalIDIssue.objects.order_by('pk').values())
        enrollment = self.enrollments[self.historical_person.pk]
        result = self.client.post(reverse('dic:operations-enrollment-id', args=[enrollment.pk]),
            {'action':'reissue', 'reason':'Must fail for deleted registration'}, content_type='application/json')
        self.assertEqual(result.status_code, 400, result.content)
        self.assertEqual(list(DigitalIDIssue.objects.order_by('pk').values()), before)
        item = self.archived.items.first()
        response = self.client.post(reverse('dic:operations-enrollments'),
            {'registration_item_id':item.pk}, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_financial_and_payment_history_is_labeled_and_never_reclassified_by_delete(self):
        data = self.get('operations-finance')
        self.assertEqual(data['summary']['registration_revenue_kobo'], 400000)
        self.assertEqual(data['summary']['net_position_kobo'], 400000)
        self.assertEqual(data['summary']['recorded_adjustments_kobo'], 0)
        self.assertEqual({row['registration_state'] for row in data['payments']}, {'Active','Archived','Deleted'})
        paid = next(row for row in data['payments'] if row['order']==str(self.deleted_paid.public_id))
        self.assertEqual(paid['payment_status'], 'paid')
        self.assertEqual(paid['verified_kobo'], 200000)
        self.assertEqual(paid['adjustment_kobo'], 0)
        rows = self.get('operations-payments')['results']
        self.assertEqual({row['registration_state'] for row in rows}, {'Active','Archived','Deleted'})
        response=self.client.get(reverse('dic:operations-finance'), {'edition':self.edition.pk,'export':'registration'})
        self.assertContains(response,'registration_state')
        self.assertContains(response,'Deleted')

    def test_audit_log_records_actor_registration_and_timestamps_for_every_lifecycle_action(self):
        self.change(self.deleted_paid, 'restore')
        self.change(self.deleted_paid, 'archive')
        self.change(self.deleted_paid, 'unarchive')
        self.change(self.deleted_paid, 'delete')
        events=DICAdminAuditEvent.objects.filter(target_type='RegistrationOrder',target_id=str(self.deleted_paid.pk),
            action__in=['registration_trashed','registration_restored','registration_test_archived','registration_unarchived'])
        self.assertEqual(events.count(),5)
        endpoint=self.client.get('/api/v1/dic/operations/activity/?page_size=100')
        self.assertEqual(endpoint.status_code,200)
        visible={row['id'] for row in endpoint.json()['results']}
        self.assertTrue(set(events.values_list('pk',flat=True)).issubset(visible))
        for event in events:
            self.assertEqual(event.actor_id,self.actor.pk)
            self.assertEqual(event.details['reference'],str(self.deleted_paid.public_id))
            self.assertIsNotNone(event.created_at)

    def test_history_permission_is_separate_from_normal_record_access(self):
        actor=get_user_model().objects.create_user('limited',is_staff=True)
        from django.contrib.auth.models import Permission
        actor.user_permissions.set(Permission.objects.filter(content_type__app_label='dic',codename__in=[
            'can_view_dic_operations','can_view_dic_ids','view_participant','view_registrationorder']))
        self.client.force_login(actor)
        for name in ('operations-check-in','operations-enrollments'):
            self.assertEqual(self.client.get(reverse('dic:'+name),{'view':'history'}).status_code,403)
            self.assertEqual(self.client.get(reverse('dic:'+name)).status_code,200)

    def test_allocation_scoring_and_reports_share_lifecycle_policy(self):
        from .allocation import paid_participants
        from .reporting_services import registration, accommodation, finance, filters
        self.assertEqual(paid_participants(self.edition).count(),2)
        registration_data=registration(self.edition,filters({},'registration'),self.actor)
        self.assertEqual(registration_data['metrics'][0]['value'],2)
        accommodation_data=accommodation(self.edition,filters({},'accommodation'),self.actor)
        self.assertEqual(accommodation_data['rows'][0]['value'],1)
        finance_data=finance(self.edition,filters({},'finance'),self.actor)
        self.assertEqual({row['registration_lifecycle'] for row in finance_data['rows']},{'active','archived','deleted'})
        self.assertEqual(DigitalIDIssue.objects.count(),2)
        self.assertTrue(HouseAllocation.objects.filter(pk=self.allocation.pk).exists())

    def test_deleted_precedence_over_archive_and_restore_policy_are_centralized(self):
        self.change(self.archived,'delete')
        self.assertEqual(lifecycle_orders().get(pk=self.archived.pk).registration_lifecycle,'deleted')
        self.change(self.archived,'restore')
        self.assertEqual(lifecycle_orders().get(pk=self.archived.pk).registration_lifecycle,'active')

    def test_active_membership_matches_central_states_without_reverse_join_duplicates(self):
        from .registration_scope import active_orders
        expected=set(lifecycle_orders().filter(registration_lifecycle='active').values_list('pk',flat=True))
        self.assertEqual(set(active_orders().values_list('pk',flat=True)),expected)
        self.assertEqual(len(expected),1)
        PaymentAttempt.objects.create(order=self.active,reference='extra-evidence-'+uuid.uuid4().hex,
            amount_kobo=200000,status='failed')
        self.assertEqual(active_orders().count(),1)

    def test_deleted_arrival_cannot_start_a_new_return_but_history_remains(self):
        from dic_movement.services import record_movement
        from dic_movement.models import Movement
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            record_movement(self.edition,self.historical_person.pk,self.actor,dict(
                action='return',confirmed=True,expected_version=0,request_id=str(uuid.uuid4())))
        self.assertFalse(Movement.objects.exists())
        self.assertTrue(CampCheckIn.objects.filter(pk=self.historical_arrival.pk).exists())

    def test_archived_paid_source_blocks_new_operational_work_and_keeps_allocated_history(self):
        self.change(self.deleted_paid,'restore')
        historical_allocation=HouseAllocation.objects.create(edition=self.edition,participant=self.historical_person,
            house=self.house,status='allocated',allocated_by=self.actor)
        self.change(self.deleted_paid,'archive')
        from .activity_scoring import eligible_members
        self.assertEqual(eligible_members(self.edition,participant_id=self.historical_person.pk),[])
        enrollment=self.enrollments[self.historical_person.pk]
        response=self.client.post(reverse('dic:operations-enrollment-id',args=[enrollment.pk]),
            {'action':'reissue','reason':'Archived paid source must not issue'},content_type='application/json')
        self.assertEqual(response.status_code,400,response.content)
        sibling=self.deleted_paid.items.exclude(participant=self.historical_person).first()
        response=self.client.post(reverse('dic:operations-check-in')+'?edition='+str(self.edition.pk),
            {'participant_id':str(sibling.participant_id)},content_type='application/json')
        self.assertEqual(response.status_code,400,response.content)
        self.assertTrue(HouseAllocation.objects.filter(pk=historical_allocation.pk).exists())
        self.assertEqual(self.get('operations-finance')['summary']['registration_revenue_kobo'],400000)
