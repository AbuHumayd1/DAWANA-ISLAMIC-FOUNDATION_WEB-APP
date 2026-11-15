"""Operations lifecycle visibility regressions; synthetic database only."""
import uuid
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .test_operations_portal import DICOperationsPortalTests as Fixtures
from .models import (RegistrationCategory, RegistrationOrderItem, PaymentAttempt,
    CampEnrollment, CampCheckIn, House, HouseAllocation)
from .participant_services import ensure_enrollment
from .campsite_api import campsite_metrics
from .registration_cleanup import (delete_disposable_registration,
    archive_test_registration)


class OperationsVisibilityTests(TestCase):
    setUp = Fixtures.setUp
    create_user = Fixtures.create_user
    make_order = Fixtures.make_order

    def manager(self):
        user = get_user_model().objects.create_superuser('visibility-owner', 'owner@example.test', 'synthetic')
        self.client.force_login(user)
        return user

    def counts(self, participants, orders):
        overview = campsite_metrics(self.edition)
        self.assertEqual(overview['registered_participants'], participants)
        response = self.client.get(reverse('dic:operations-dashboard'), {'edition': self.edition.pk})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['metrics']['participants'], participants)
        self.assertEqual(response.json()['metrics']['orders'], orders)
        for ordering in ('name', 'date', '-date'):
            response = self.client.get(reverse('dic:operations-participants'),
                {'edition': self.edition.pk, 'ordering': ordering})
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()['count'], participants)
        self.assertEqual(self.client.get(reverse('dic:operations-registrations'),
            {'edition': self.edition.pk}).json()['count'], orders)
        return overview

    def change(self, order, action):
        names = {'delete': 'operations-registration-delete',
            'restore': 'operations-registration-restore-deleted',
            'archive': 'operations-registration-archive-test',
            'unarchive': 'operations-registration-unarchive'}
        response = self.client.post(reverse('dic:' + names[action], args=[order.public_id]),
            {'confirmation': str(order.public_id), 'reason': 'Synthetic lifecycle regression'},
            content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)

    def test_pending_delete_restore_archive_unarchive_updates_all_active_views(self):
        self.manager()
        self.counts(3, 2)
        for hide, show in [('delete', 'restore'), ('archive', 'unarchive')]:
            self.change(self.unpaid_order, hide)
            overview = self.counts(2, 1)
            self.assertEqual(overview['awaiting_payment_verification'], 0)
            self.assertEqual(overview['requiring_attention'], 0)
            self.change(self.unpaid_order, show)
            self.counts(3, 2)

    def test_paid_multi_participant_booking_and_protected_records_are_retained(self):
        actor = self.manager()
        item = self.paid_order.items.first()
        enrollment = ensure_enrollment(item.pk)
        from .identity_cards import command
        issue = command(enrollment, 'issue', actor, 'Synthetic regression')
        issue_before = type(issue).objects.filter(pk=issue.pk).values().get()
        checkin = CampCheckIn.objects.create(participant=item.participant, edition=self.edition, checked_in_by=actor)
        self.edition.housing_age_reference_date = self.edition.camp_start_date
        self.edition.save(update_fields=['housing_age_reference_date'])
        house = House.objects.create(edition=self.edition, name='Synthetic House', gender='male', capacity=20)
        allocation = HouseAllocation.objects.create(participant=item.participant, edition=self.edition,
            house=house, allocated_by=actor, status='allocated')
        original = list(PaymentAttempt.objects.filter(order=self.paid_order).values())
        for hide, show in [('delete', 'restore'), ('archive', 'unarchive')]:
            self.change(self.paid_order, hide)
            self.counts(1, 1)
            self.assertEqual(list(PaymentAttempt.objects.filter(order=self.paid_order).values()), original)
            self.assertTrue(CampEnrollment.objects.filter(pk=enrollment.pk).exists())
            self.assertEqual(type(issue).objects.filter(pk=issue.pk).values().get(), issue_before)
            self.assertTrue(CampCheckIn.objects.filter(pk=checkin.pk).exists())
            self.assertTrue(HouseAllocation.objects.filter(pk=allocation.pk).exists())
            self.assertEqual(self.paid_order.items.count(), 2)
            metrics = self.client.get(reverse('dic:operations-dashboard')).json()['metrics']
            self.assertEqual(metrics['allocated_participants'], 0)
            self.assertEqual(metrics['eligible_unallocated_participants'], 0)
            self.change(self.paid_order, show)
            self.counts(3, 2)

    def test_hidden_payment_states_cannot_leak_into_attention_or_participant_filters(self):
        actor = self.manager()
        for state in ('pending', 'failed', 'amount_mismatch', 'reconcile', 'init_unknown', 'successful'):
            order = self.make_order(('Hidden ' + state,), paid=False)
            PaymentAttempt.objects.create(order=order, reference='scope-'+uuid.uuid4().hex,
                amount_kobo=12500, status=state)
            delete_disposable_registration(order.public_id, actor, str(order.public_id), 'Synthetic')
        self.counts(3, 2)
        data = self.client.get(reverse('dic:operations-dashboard')).json()
        self.assertEqual(data['metrics']['reconciliation_cases'], 0)
        self.assertTrue(all(row['reference'] == str(self.unpaid_order.public_id) for row in data['attention']))

    def test_archive_all_trash_and_restore_precedence(self):
        self.manager()
        for action, expected in [('archive', (1, 2, 1, 0)), ('delete', (1, 1, 0, 1)),
                ('restore', (2, 2, 0, 0)), ('archive', (1, 2, 1, 0)), ('unarchive', (2, 2, 0, 0))]:
            self.change(self.unpaid_order, action)
            counts = tuple(self.client.get(reverse('dic:operations-registrations'),
                {'archive': view}).json()['count'] for view in ('active', 'all', 'archived', 'trash'))
            self.assertEqual(counts, expected)

    def test_shared_participant_uses_only_active_items_and_does_not_duplicate_on_date_sort(self):
        actor = self.manager()
        participant = self.paid_order.items.first().participant
        hidden_item = self.unpaid_order.items.first()
        RegistrationOrderItem.objects.create(order=self.unpaid_order, participant=participant,
            category=self.category, category_name_snapshot=self.category.name,
            fee_snapshot_ngn=self.category.fee_ngn, participant_snapshot={})
        archive_test_registration(self.unpaid_order.public_id, actor, str(self.unpaid_order.public_id), 'Synthetic')
        self.counts(2, 1)
        detail = self.client.get(reverse('dic:operations-participant-detail', args=[participant.pk])).json()
        self.assertEqual(detail['registration_reference'], str(self.paid_order.public_id))
        self.assertEqual(len(detail['registrations']), 1)
        self.assertEqual(self.client.get(reverse('dic:operations-participants'),
            {'payment_status': 'pending'}).json()['count'], 0)

    def test_non_deleted_order_in_other_edition_cannot_reveal_hidden_participant(self):
        actor = self.manager()
        item = self.unpaid_order.items.first()
        other = type(self.edition).objects.create(name='Other', year=2096,
            camp_start_date=self.edition.camp_start_date, camp_end_date=self.edition.camp_end_date)
        order = self.make_order(('Other',), paid=False)
        order.edition = other
        order.save(update_fields=['edition'])
        category = RegistrationCategory.objects.create(edition=other, name='Other', fee_ngn=125)
        RegistrationOrderItem.objects.create(order=order, participant=item.participant,
            category=category, category_name_snapshot=self.category.name,
            fee_snapshot_ngn=self.category.fee_ngn, participant_snapshot={})
        delete_disposable_registration(self.unpaid_order.public_id, actor, str(self.unpaid_order.public_id), 'Synthetic')
        self.counts(2, 1)

    def test_expired_and_cancelled_orders_are_excluded_from_active_statistics(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import OrderExpiryPolicy, RegistrationOrder
        self.manager()
        OrderExpiryPolicy.objects.create(activated_at=timezone.now())
        RegistrationOrder.objects.filter(pk=self.unpaid_order.pk).update(
            created_at=timezone.now() - timedelta(hours=25))
        self.counts(2, 1)
        self.assertEqual(self.client.get(reverse('dic:operations-registrations'),
            {'archive': 'expired'}).json()['count'], 1)
        RegistrationOrder.objects.filter(pk=self.unpaid_order.pk).update(status='cancelled')
        self.counts(2, 1)
        self.assertEqual(self.client.get(reverse('dic:operations-registrations'),
            {'archive': 'all'}).json()['count'], 2)

    def test_admin_overview_uses_the_same_active_scope(self):
        actor = self.manager()
        delete_disposable_registration(self.unpaid_order.public_id, actor,
            str(self.unpaid_order.public_id), 'Synthetic')
        response = self.client.get(reverse('dic_operations_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_orders'], 1)
        self.assertEqual(response.context['individual_participants'], 2)

    def test_reporting_overview_excludes_hidden_registrations(self):
        from .reporting_services import registration, filters
        actor = self.manager()
        archive_test_registration(self.unpaid_order.public_id, actor,
            str(self.unpaid_order.public_id), 'Synthetic')
        result = registration(self.edition, filters({}, 'registration'), actor)
        metrics = {row['label']: row['value'] for row in result['metrics']}
        self.assertEqual(metrics['Registered participants'], 2)
        self.assertEqual(metrics['Bookings'], 1)
