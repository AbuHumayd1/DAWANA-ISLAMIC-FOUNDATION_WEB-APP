from datetime import datetime, timezone as utc
from decimal import Decimal
from contextlib import nullcontext
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings
from .models import AcademicAssignment, AcademicClass, CampAnnouncement, CampEdition, FoundationDonation
from .foundation_api import (official_channels, donation_limits, donation_ready, verified_status,
    valid_checkout, DonationInput, EnquiryInput, settle_donation)
from .launch_admin import ClassAdmin, AnnouncementAdmin
from .launch_services import assigned_class


class LaunchCompletionPolicyTests(SimpleTestCase):
    def test_public_writes_require_csrf_before_storage(self):
        from rest_framework.test import APIRequestFactory
        from .foundation_api import DonationCreate, EnquiryView
        factory=APIRequestFactory(enforce_csrf_checks=True)
        for view in (DonationCreate,EnquiryView):
            response=view.as_view()(factory.post('/api/v1/foundation/',{},format='json'))
            self.assertEqual(response.status_code,403)

    def test_donation_status_requires_secret_and_hides_unknown_records(self):
        from .foundation_api import DonationStatus
        from rest_framework.exceptions import NotFound
        with patch('dic.foundation_api.require_donations'),patch('dic.foundation_api.FoundationDonation.objects') as rows:
            rows.filter.return_value.first.return_value=None
            with self.assertRaises(NotFound): DonationStatus().authorized(NS(headers={'X-Donation-Token':'x'*64}),'foundation-donation-synthetic')
            self.assertNotEqual(rows.filter.call_args.kwargs['token_digest'],'x'*64)

    def test_import_and_publication_preview_never_access_database(self):
        from .management.commands.publish_dic2026_timetables import Command as Publish
        from .management.commands.import_dic2026_timetables import Command as Import
        Import().handle(edition=1,apply=False)
        Publish().handle(edition=1,apply=False)

    @override_settings(FOUNDATION_CONTACT_VERIFIED=False)
    def test_operator_contacts_are_verified_not_whatsapp_inferred(self):
        channels=official_channels()
        self.assertEqual(channels['email'],'dawanaislamicfoundation@gmail.com')
        self.assertEqual(channels['phones'],['+2347062956559','+2348105320528','+2349018076534'])
        self.assertNotIn('whatsapp',channels)

    @override_settings(FOUNDATION_CONTACT_VERIFIED=True,FOUNDATION_CONTACT_EMAIL='invalid',FOUNDATION_CONTACT_PHONE='javascript:bad',FOUNDATION_CONTACT_WHATSAPP='bad')
    def test_invalid_channel_overrides_not_rendered(self):
        channels=official_channels()
        self.assertNotIn('email',channels); self.assertNotIn('phone',channels); self.assertNotIn('whatsapp',channels)

    @override_settings(FOUNDATION_DONATIONS_ENABLED=False)
    def test_donations_default_off(self): self.assertFalse(donation_ready())

    @override_settings(FOUNDATION_DONATIONS_ENABLED=True,FOUNDATION_DONATION_CURRENCY='NGN',FOUNDATION_DONATION_MIN_NGN='0.01',FOUNDATION_DONATION_MAX_NGN='92233720368547758.07',PAYSTACK_MODE='live')
    def test_live_collection_always_rejected(self): self.assertFalse(donation_ready())

    @override_settings(FOUNDATION_DONATION_MIN_NGN='0.01',FOUNDATION_DONATION_MAX_NGN='92233720368547758.07')
    def test_any_representable_amount_limits(self):
        self.assertEqual(donation_limits(),(Decimal('0.01'),Decimal('92233720368547758.07')))

    def test_invalid_money_configuration_rejected(self):
        for minimum,maximum in [('NaN','1'),('0','1'),('1','0.5'),('0.001','1'),('1','Infinity')]:
            with self.subTest(minimum=minimum), self.settings(FOUNDATION_DONATION_MIN_NGN=minimum,FOUNDATION_DONATION_MAX_NGN=maximum):
                self.assertIsNone(donation_limits())

    def test_donation_input_requires_private_token_and_valid_amount(self):
        data=dict(request_id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',access_token='x'*64,email='donor@example.test',amount='0.01')
        self.assertTrue(DonationInput(data=data).is_valid())
        for key,value in [('amount','0'),('amount','1.001'),('access_token','short'),('email','bad')]:
            self.assertFalse(DonationInput(data={**data,key:value}).is_valid())

    def test_contact_validation(self):
        data=dict(name='Synthetic Sender',email='sender@example.test',subject='Synthetic enquiry',message='Synthetic enquiry for tests.')
        self.assertTrue(EnquiryInput(data=data).is_valid())
        self.assertFalse(EnquiryInput(data={**data,'message':'short'}).is_valid())
        self.assertFalse(EnquiryInput(data={**data,'email':'invalid'}).is_valid())

    def row_and_proof(self):
        row=NS(reference='foundation-donation-synthetic',amount_kobo=100,status='pending',audit=[])
        proof=dict(reference=row.reference,amount=100,currency='NGN',domain='test',status='success')
        return row,proof

    def test_success_pending_failed_abandoned(self):
        row,data=self.row_and_proof()
        for status,result in [('success','successful'),('pending','pending'),('failed','failed'),('abandoned','abandoned')]:
            self.assertEqual(verified_status(row,{**data,'status':status}),result)

    def test_mismatched_amount_reference_currency_domain_never_settle(self):
        row,data=self.row_and_proof()
        for key,value in [('amount',101),('amount',True),('reference','dic-registration'),('currency','USD'),('domain','live')]:
            self.assertEqual(verified_status(row,{**data,key:value}),'review')

    def test_duplicate_settlement_never_mutates_success(self):
        row,data=self.row_and_proof(); row.status='successful'; row.save=Mock()
        with patch('dic.foundation_api.FoundationDonation.objects') as objects:
            objects.select_for_update.return_value.get.return_value=row
            result=settle_donation.__wrapped__(row.reference,data)
            self.assertIs(result,row); row.save.assert_not_called(); self.assertEqual(row.audit,[])

    def test_create_replay_initializes_provider_once(self):
        from .foundation_api import DonationCreate, digest
        data=dict(request_id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',access_token='x'*64,email='donor@example.test',amount='1.00')
        row=NS(status='created',reference='foundation-donation-synthetic',fingerprint=digest(json.dumps(['1.00','donor@example.test'])),
            token_digest=digest('x'*64),email='donor@example.test',amount_kobo=100,currency='NGN',authorization_url='',audit=[],save=Mock(),pk=1)
        with patch('dic.foundation_api.require_donations'),patch('dic.foundation_api.donation_limits',return_value=(Decimal('.01'),Decimal('100'))),patch('dic.foundation_api.transaction.atomic',side_effect=lambda:nullcontext()),patch('dic.foundation_api.FoundationDonation.objects') as rows,patch('dic.foundation_api.PaystackClient') as provider:
            rows.get_or_create.return_value=(row,True); rows.select_for_update.return_value.get.return_value=row
            provider.return_value.initialize_transaction.return_value={'reference':row.reference,'authorization_url':'https://checkout.paystack.com/synthetic'}
            first=DonationCreate().post(NS(data=data)); second=DonationCreate().post(NS(data=data))
            self.assertEqual(first.data['reference'],second.data['reference'])
            self.assertEqual(row.status,'pending'); provider.return_value.initialize_transaction.assert_called_once()

    def test_donation_webhook_rejects_signature_before_verification(self):
        from .foundation_api import DonationWebhook
        from rest_framework.exceptions import PermissionDenied
        with patch('dic.foundation_api.require_donations'),patch('dic.foundation_api.PaystackClient') as provider:
            provider.return_value.secret_key='synthetic-secret'
            with self.assertRaises(PermissionDenied): DonationWebhook().post(NS(body=b'{}',headers={'X-Paystack-Signature':'invalid'},data={}))
            provider.return_value.verify_transaction.assert_not_called()

    def test_checkout_redirect_allowlist(self):
        self.assertTrue(valid_checkout('https://checkout.paystack.com/synthetic'))
        for url in ['javascript:alert(1)','https://checkout.paystack.com.evil.test/x','http://checkout.paystack.com/x','https://user@checkout.paystack.com/x','https://checkout.paystack.com:444/x']:
            self.assertFalse(valid_checkout(url))

    def test_class_requires_same_edition_and_active(self):
        cls=AcademicClass(pk=1,edition_id=2,name='Operator-defined class',active=True)
        assignment=AcademicAssignment(edition_id=3,academic_class=cls)
        with self.assertRaises(ValidationError): assignment.clean()
        assignment.edition_id=2; cls.active=False
        with self.assertRaises(ValidationError): assignment.clean()

    def test_class_requires_registered_camper_not_tutor(self):
        with patch('dic.models.RegistrationOrderItem.objects') as items:
            items.filter.return_value.exclude.return_value.exists.return_value=False
            with self.assertRaises(ValidationError): AcademicAssignment(edition_id=1,participant_id=4).clean()
            items.filter.return_value.exclude.assert_called_once_with(order__registration_basis='tutor')

    def test_assignment_projection_is_edition_scoped_and_read_only(self):
        with patch('dic.launch_services.connection') as connection, patch('dic.launch_services.AcademicAssignment.objects') as assignments:
            connection.introspection.table_names.return_value=[AcademicClass._meta.db_table,AcademicAssignment._meta.db_table]
            assignments.select_related.return_value.filter.return_value.first.return_value=NS(academic_class=NS(name='Approved class'))
            result=assigned_class(4,NS(pk=7))
            self.assertEqual(result['status'],'assigned'); self.assertEqual(result['name'],'Approved class')
            query=assignments.select_related.return_value.filter.call_args.kwargs
            self.assertEqual(query['participant_id'],4); self.assertIs(query['edition'],query['academic_class__edition'])
            assignments.create.assert_not_called()

    def test_admin_permissions_separate_edit_publish(self):
        request=NS(user=Mock(is_active=True,is_staff=True))
        request.user.has_perm.side_effect=lambda perm:perm=='dic.manage_dic_classes'
        self.assertTrue(ClassAdmin(AcademicClass,AdminSite()).has_change_permission(request))
        admin=AnnouncementAdmin(CampAnnouncement,AdminSite())
        self.assertFalse(admin.has_add_permission(request))
        request.user.has_perm.side_effect=lambda perm:perm=='dic.publish_dic_announcements'
        self.assertTrue(admin.has_view_permission(request)); self.assertFalse(admin.has_change_permission(request))

    def test_announcement_requires_ordered_window_and_deliberate_publish(self):
        with self.assertRaises(ValidationError): CampAnnouncement(starts_at=datetime(2026,12,24,tzinfo=utc.utc),ends_at=datetime(2026,12,23,tzinfo=utc.utc)).clean()
        with self.assertRaises(ValidationError): CampAnnouncement(status='published').save()

    def test_announcement_reader_requires_guardian_scope(self):
        from .launch_api import CampUpdatesView
        from rest_framework.exceptions import PermissionDenied
        with patch('dic.launch_api.portal_item',side_effect=PermissionDenied):
            with self.assertRaises(PermissionDenied): CampUpdatesView().get(NS(query_params={'item_id':'42'}))

    def test_announcement_reader_filters_drafts_and_other_editions(self):
        from .launch_api import CampUpdatesView
        item=NS(order=NS(edition=NS(pk=1),registration_basis='paid'),participant_id=4)
        with patch('dic.launch_api.portal_item',return_value=item),patch('dic.launch_api.connection') as connection,patch('dic.launch_api.CampAnnouncement.objects') as announcements,patch('dic.launch_api.assigned_class',return_value={'status':'unassigned'}):
            connection.introspection.table_names.return_value=[CampAnnouncement._meta.db_table]
            announcements.filter.return_value.filter.return_value.filter.return_value=[]
            response=CampUpdatesView().get(NS(query_params={'item_id':'42','edition':'999'}))
            announcements.filter.assert_called_once_with(edition=item.order.edition,status='published')
            self.assertEqual(response.data['announcements'],[])
