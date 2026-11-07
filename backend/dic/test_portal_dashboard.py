"""CP-1 projection tests; integration fixtures run in isolated test DB only."""
from types import SimpleNamespace as NS
from unittest.mock import patch
from uuid import uuid4
from django.test import SimpleTestCase,TestCase,Client,override_settings
from django.urls import reverse
from django.utils import timezone
from .portal_dashboard import camper_operations_summary
from .test_participant_portal import PortalFixtures,TEST_DELIVERY
from .models import CampCheckIn,ParticipantPortalGrant,CampEnrollment


class CamperProjectionTests(SimpleTestCase):
    def setUp(self):
        # This fixture represents an ordinary participant, not a tutor. Keep the
        # real projection and its housing/check-in query boundaries under test.
        self.tutor_items = self.enterContext(patch('dic.tutor_registration.RegistrationOrderItem.objects'))
        self.tutor_items.filter.return_value.exists.return_value = False

    def test_projection_is_participant_edition_scoped_minimal_and_read_only(self):
        edition=NS(pk=41)
        with patch('dic.portal_dashboard.HouseAllocation.objects') as allocations,patch('dic.portal_dashboard.CampCheckIn.objects') as arrivals:
            allocations.filter.return_value.select_related.return_value.__getitem__.return_value=[NS(house=NS(name='Approved House',badge_colour='#147D64'))]
            arrivals.filter.return_value.exists.return_value=True
            result=camper_operations_summary('person',edition)
            self.assertEqual(result,dict(house_assignment=dict(name='Approved House',colour='#147D64'),checked_in=True))
            self.assertEqual(allocations.filter.call_args.kwargs['participant_id'],'person')
            self.assertEqual(allocations.filter.call_args.kwargs['edition'],edition)
            self.assertEqual(allocations.filter.call_args.kwargs['status'],'allocated')
            self.assertEqual(allocations.filter.call_args.kwargs['house__edition'],edition)
            arrivals.filter.assert_called_once_with(participant_id='person',edition=edition)
            self.tutor_items.filter.assert_called_once_with(participant_id='person',
                order__edition_id=edition.pk, order__registration_basis='tutor')
            allocations.create.assert_not_called();arrivals.create.assert_not_called()

    def test_tutor_projection_does_not_return_competitive_housing_fields(self):
        self.tutor_items.filter.return_value.exists.return_value = True
        with patch('dic.portal_dashboard.HouseAllocation.objects') as allocations, \
                patch('dic.portal_dashboard.CampCheckIn.objects') as arrivals:
            arrivals.filter.return_value.exists.return_value = True
            result = camper_operations_summary('person', NS(pk=41))
        self.assertEqual(result, dict(registration_basis='tutor', competitive=False, checked_in=True))
        allocations.filter.assert_not_called()

    def test_unassigned_ambiguous_and_invalid_colour_states(self):
        for rows,expected in [([],None),([NS(house=NS(name='House',badge_colour='invalid'))],dict(name='House',colour=None)),([NS(),NS()],None)]:
            with patch('dic.portal_dashboard.HouseAllocation.objects') as allocations,patch('dic.portal_dashboard.CampCheckIn.objects') as arrivals:
                allocations.filter.return_value.select_related.return_value.__getitem__.return_value=rows
                arrivals.filter.return_value.exists.return_value=False
                result=camper_operations_summary('person',NS(pk=1))
                self.assertEqual(result,dict(house_assignment=expected,checked_in=False))


@override_settings(**TEST_DELIVERY)
class CamperDashboardIntegrationTests(PortalFixtures,TestCase):
    def test_booking_summary_shows_each_campers_arrival_without_staff_metadata_or_id(self):
        person=self.paid_order.items.first().participant
        CampCheckIn.objects.create(participant=person,edition=self.edition,checked_in_by=self.id_manager)
        client,_=self.login()
        response=client.get(reverse('dic:participant-enrollments'))
        self.assertEqual(response.status_code,200)
        people=response.json()['orders'][0]['participants']
        by_item={row['registration_item_id']:row for row in people}
        self.assertTrue(by_item[self.paid_order.items.first().pk]['checked_in'])
        self.assertEqual(sum(row['checked_in'] for row in people),1)
        self.assertTrue(all(row['house_assignment'] is None for row in people))
        self.assertEqual(CampEnrollment.objects.count(),0)
        for private in ('checked_in_by','checked_in_at','assigned_to','verification_secret','allocation_queue'):
            self.assertNotIn(private,str(response.json()))

    def test_foreign_arrival_is_not_returned_and_expired_or_revoked_session_is_denied(self):
        CampCheckIn.objects.create(participant=self.unpaid_order.items.first().participant,edition=self.edition,checked_in_by=self.id_manager)
        client,_=self.login()
        people=client.get(reverse('dic:participant-enrollments')).json()['orders'][0]['participants']
        self.assertFalse(any(row['checked_in'] for row in people))
        ParticipantPortalGrant.objects.update(expires_at=timezone.now())
        self.assertEqual(client.get(reverse('dic:participant-enrollments')).status_code,403)

    def test_revoked_session_is_denied_with_its_own_verified_booking_fixture(self):
        # A second login for the same contact would correctly hit the 60-second
        # production cooldown. Keep revocation independent from the expiry test
        # so each case uses one real OTP login and a fresh per-test contact.
        client,_=self.login()
        ParticipantPortalGrant.objects.update(revoked_at=timezone.now())
        self.assertEqual(client.get(reverse('dic:participant-enrollments')).status_code,403)

    def test_anonymous_and_foreign_enrollment_requests_cannot_access_summary_fields(self):
        response=Client().get(reverse('dic:participant-enrollments'))
        self.assertEqual(response.status_code,403)
        self.assertNotIn('checked_in',str(response.content));self.assertNotIn('house_assignment',str(response.content))
        client,_=self.login()
        self.assertEqual(client.get(reverse('dic:participant-id',args=[uuid4()])).status_code,404)

    def test_house_fields_are_only_projected_for_verified_booking_items(self):
        allowed=set(self.paid_order.items.values_list('participant_id',flat=True))
        with patch('dic.portal_dashboard.camper_operations_summary',return_value=dict(house_assignment=dict(name='Scoped',colour='#147D64'),checked_in=False)) as project:
            client,_=self.login();response=client.get(reverse('dic:participant-enrollments'))
        self.assertEqual(response.status_code,200)
        self.assertEqual({call.args[0] for call in project.call_args_list},allowed)
        self.assertTrue(all(call.args[1].pk==self.edition.pk for call in project.call_args_list))
