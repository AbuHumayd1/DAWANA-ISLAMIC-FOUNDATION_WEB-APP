from unittest.mock import patch
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework.exceptions import NotFound, ValidationError
from .tests import PaymentApiTests
from .payment_views import _apply_verified_transaction
from .tickets import ticket_rows, ticket_pdf, ticket_token, resolve_ticket

@override_settings(PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_unit_mock')
class TicketTests(APITestCase):
    setUp = PaymentApiTests.setUp
    create_pending_attempt = PaymentApiTests.create_pending_attempt
    provider_result = PaymentApiTests.provider_result

    def settle(self):
        attempt = self.create_pending_attempt()
        _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference))
        self.order.refresh_from_db()

    def test_unpaid_order_cannot_generate_ticket(self):
        with self.assertRaises(NotFound):
            ticket_pdf(self.order)

    def test_verified_payment_generates_group_and_individual_pdf(self):
        self.settle()
        rows = ticket_rows(self.order)
        self.assertTrue(rows)
        self.assertEqual(sum(fee for _, fee in rows), self.order.total_amount_ngn)
        self.assertTrue(ticket_pdf(self.order).content.startswith(b'%PDF-'))
        item = rows[0][0]
        self.assertTrue(ticket_pdf(self.order, item.pk).content.startswith(b'%PDF-'))
        with self.assertRaises(NotFound):
            ticket_pdf(self.order, 999999999)
        self.assertEqual(resolve_ticket(ticket_token(item), self.order.edition).pk, item.pk)
        with self.assertRaises(ValidationError):
            resolve_ticket(ticket_token(item)+'tampered', self.order.edition)
        self.order.payment_status = 'refunded'
        self.order.save(update_fields=['payment_status'])
        with self.assertRaises(ValidationError):
            resolve_ticket(ticket_token(item), self.order.edition)

    def test_single_booking_has_compact_landscape_ticket(self):
        self.settle()
        rows = ticket_rows(self.order)
        if len(rows) == 1:
            pdf = ticket_pdf(self.order)
            self.assertIn(b'/MediaBox [ 0 0 648 324 ]', pdf.content)
            self.assertIn(str(rows[0][0].pk)+'.pdf', pdf['Content-Disposition'])
