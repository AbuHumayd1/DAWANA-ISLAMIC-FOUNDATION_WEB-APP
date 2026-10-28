"""Response finalization regressions. SimpleTestCase forbids database access."""
from django.http import HttpResponse
from django.test import SimpleTestCase, RequestFactory
from .identity_views import secured
from .operations_api import OperationsBaseView
from .printing_api import PrintingExportView


class PrintingCacheControlTests(SimpleTestCase):
    def finalize(self, view_class, response):
        view = view_class()
        view.headers = view.default_response_headers
        return view.finalize_response(RequestFactory().post('/'), response)

    def test_bulk_pdf_keeps_private_no_store_after_finalization(self):
        payload = b'%PDF-synthetic-header-test'
        response = HttpResponse(payload, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="test-batch.pdf"'
        response['X-ID-Batch'] = 'synthetic-batch'
        secured(response)
        finalized = self.finalize(PrintingExportView, response)
        self.assertIs(finalized, response)
        self.assertEqual(finalized['Cache-Control'], 'private, no-store')
        self.assertEqual(finalized['Pragma'], 'no-cache')
        self.assertEqual(finalized.content, payload)
        self.assertEqual(finalized['Content-Type'], 'application/pdf')
        self.assertEqual(finalized['Content-Disposition'], 'attachment; filename="test-batch.pdf"')
        self.assertEqual(finalized['X-ID-Batch'], 'synthetic-batch')
        self.assertEqual(finalized['X-Content-Type-Options'], 'nosniff')

    def test_operations_default_still_enforces_no_store(self):
        response = self.finalize(OperationsBaseView, HttpResponse('{}', content_type='application/json'))
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(response['Pragma'], 'no-cache')

    def test_finalizer_adds_no_store_without_dropping_private_directives(self):
        response = HttpResponse()
        response['Cache-Control'] = 'private, must-revalidate'
        response = self.finalize(OperationsBaseView, response)
        self.assertEqual(response['Cache-Control'], 'private, must-revalidate, no-store')
