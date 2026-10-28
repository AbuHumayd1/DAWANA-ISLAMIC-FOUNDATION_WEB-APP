"""Standard-library-only regression tests. No Django setup or database access."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from types import ModuleType, SimpleNamespace
import sys
import io
from contextlib import redirect_stdout

spec = importlib.util.spec_from_file_location('tutor_evidence',
    Path(__file__).resolve().parents[1] / 'backend/dic/tutor_validation_evidence.py')
evidence_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence_module)


class ConcurrencyEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.database = 'test_dic_tutor_20261026232748_eca18069'
        self.receipt = dict(database=self.database, status=evidence_module.STATUS, order='order-uuid', authorization='auth-uuid')
        self.rows = {table: [] for table in evidence_module.EXPECTED_COUNTS}
        self.rows.update({
            'accounts_user': [dict(id=1, username='synthetic-tutor-authorizer', is_staff=True, is_active=True, is_superuser=False, password='!unusable')],
            'dic_campedition': [dict(id=2, name='SYNTHETIC tutors', year=2097, tutor_registration_enabled=True, is_active=True, registration_status='closed')],
            'dic_tutorregistrationauthorization': [dict(id='auth-uuid', edition_id=2, authorized_by_id=1,
                enrollment_id='enrollment-uuid', revoked_at=None, revoked_by_id=None, revocation_reason='',
                intended_name='Synthetic Tutor', email='tutor@example.test', reason='Approved synthetic tutor',
                invitation_digest='a'*64, authorized_at='2026-10-26 12:00:00+00:00', issued_at='2026-10-26 12:00:01+00:00',
                expires_at='2026-11-02 12:00:01+00:00', verified_at='2026-10-26 12:00:02+00:00', redeemed_at='2026-10-26 12:00:03+00:00')],
            'dic_tutorverification': [dict(id='verification-uuid', authorization_id='auth-uuid', verified_at='2026-10-26 12:00:02+00:00',
                invitation_digest='a'*64, browser_digest='b'*64, capability_digest='c'*64, request_fingerprint='d'*64, code_digest='')],
            'dic_primaryregistrant': [dict(id=4, full_name='Synthetic Tutor', email='tutor@example.test', phone='08012345678')],
            'dic_registrationorder': [dict(id=5, public_id='order-uuid', edition_id=2, registration_basis='tutor',
                status='confirmed', payment_status='not_required', current_price_revision_id=None,
                access_token_revoked_at=None, primary_registrant_id=4, request_fingerprint='d'*64)],
            'dic_registrationcategory': [dict(id=6, edition_id=2, name='DIC Tutor', is_active=False, fee_ngn='0.00')],
            'dic_registrationorderitem': [dict(id=7, order_id=5, participant_id='participant-uuid', category_id=6,
                category_name_snapshot='DIC Tutor', fee_snapshot_ngn='0.00')],
            'dic_campenrollment': [dict(id='enrollment-uuid', participant_id='participant-uuid', edition_id=2,
                source_item_id=7, restriction_reason='', source_review_fingerprint='')],
        })
        participant = dict(id='participant-uuid', full_name='Synthetic Tutor', email='tutor@example.test',
            address='Synthetic', phone='08012345678', date_of_birth=None, sex='Female', height_cm=None, weight_kg=None,
            academic_status='Tertiary Student', occupation='None', marital_status='None', age_declaration='adult', adult_declared_on='2026-10-26')
        self.rows['dic_participant'] = [participant]
        self.rows['dic_registrationorderitem'][0]['participant_snapshot'] = {k:v for k,v in participant.items() if k != 'id'}
        ctypes = sorted({(app, model) for app, model, code in evidence_module.PERMISSIONS})
        self.rows['django_content_type'] = [dict(id=i, app_label=app, model=model) for i, (app, model) in enumerate(ctypes, 1)]
        for i, (app, model, code) in enumerate(sorted(evidence_module.PERMISSIONS), 1):
            self.rows['auth_permission'].append(dict(id=i, content_type_id=ctypes.index((app, model))+1, codename=code))
            self.rows['accounts_user_user_permissions'].append(dict(id=i, user_id=1, permission_id=i))
        for i, action in enumerate(['tutor_authorized', 'tutor_issued', 'tutor_redeemed', 'participant_enrollment_created'], 1):
            self.rows['dic_dicadminauditevent'].append(dict(id=i, action=action,
                target_type='CampEnrollment' if i == 4 else 'TutorRegistrationAuthorization',
                target_id='enrollment-uuid' if i == 4 else 'auth-uuid', actor_id=1 if i < 3 else None,
                details={'order': 'order-uuid', 'enrollment': 'enrollment-uuid'} if i == 3 else {}))
        self.rows['dic_dicadminauditevent'][0]['details'] = {'reason': 'Approved synthetic tutor'}
        self.rows['dic_dicadminauditevent'][1]['details'] = dict(reason='Initial synthetic invitation',
            previous_digest=None, expires_at='2026-11-02T12:00:01+00:00')

    def validate(self, receipt=None):
        return evidence_module.validate(self.rows, receipt or self.receipt, self.database, 'creation-hash')

    def test_successful_legacy_concurrency_evidence_is_retained_and_accepted(self):
        before = deepcopy(self.rows)
        self.assertIn('legacy', self.validate())
        self.assertEqual(self.rows, before)

    def test_new_evidence_is_bound_to_creation_receipt_and_all_rows(self):
        receipt = dict(self.receipt, creation_receipt_sha256='creation-hash', snapshot_sha256=evidence_module.snapshot_digest(self.rows))
        self.assertEqual(self.validate(receipt), 'bound snapshot')
        self.rows['dic_participant'][0]['address'] = 'Unexpected edit'
        with self.assertRaises(RuntimeError): self.validate(receipt)

    def test_extra_business_or_privilege_records_are_rejected(self):
        for table in ['dic_participant', 'dic_registrationorder', 'dic_campcheckin', 'dic_houseallocation',
                      'dic_housingjob', 'dic_payments', 'dic_paymentattempt', 'dic_registrationorderpricerevision',
                      'dic_movement_movement', 'dic_scoring_activityaward', 'auth_group', 'accounts_user']:
            with self.subTest(table=table):
                snapshot = deepcopy(self.rows)
                self.rows.setdefault(table, []).append({'id': 'unexpected'})
                with self.assertRaises(RuntimeError): self.validate()
                self.rows = snapshot

    def test_wrong_database_partial_or_unbound_receipts_are_rejected(self):
        for change in [dict(database='dawana_dev'), dict(status='reserved; retain all partial evidence'),
                       dict(order='other-order'), dict(authorization='other-auth'),
                       dict(snapshot_sha256='incomplete'), dict(creation_receipt_sha256='wrong', snapshot_sha256=evidence_module.snapshot_digest(self.rows))]:
            with self.subTest(change=change), self.assertRaises(RuntimeError): self.validate(dict(self.receipt, **change))

    def test_changed_payment_source_authorization_and_permissions_are_rejected(self):
        for table, field, value in [('dic_registrationorder', 'payment_status', 'paid'),
                ('dic_registrationorderitem', 'fee_snapshot_ngn', '100'),
                ('dic_campenrollment', 'source_item_id', 999),
                ('dic_tutorregistrationauthorization', 'revoked_at', '2026-10-27'),
                ('auth_permission', 'content_type_id', 999), ('accounts_user', 'is_superuser', True)]:
            with self.subTest(table=table, field=field):
                snapshot = deepcopy(self.rows)
                self.rows[table][0][field] = value
                with self.assertRaises(RuntimeError): self.validate()
                self.rows = snapshot

    def test_missing_duplicate_audits_or_snapshot_mismatch_are_rejected(self):
        for kind in ('missing', 'duplicate', 'snapshot'):
            with self.subTest(kind=kind):
                snapshot = deepcopy(self.rows)
                if kind == 'missing': self.rows['dic_dicadminauditevent'].pop()
                elif kind == 'duplicate': self.rows['dic_dicadminauditevent'][0]['action'] = 'tutor_redeemed'
                else: self.rows['dic_registrationorderitem'][0]['participant_snapshot']['age_declaration'] = 'minor'
                with self.assertRaises(RuntimeError): self.validate()
                self.rows = snapshot

    def verify_context(self, readonly=True, extra_migration=False):
        runner_spec = importlib.util.spec_from_file_location('tutor_runner', Path(__file__).with_name('validate_dic_tutor_registration.py'))
        runner = importlib.util.module_from_spec(runner_spec)
        runner_spec.loader.exec_module(runner)
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.fetchone.side_effect = [(None,) * 6, ('on' if readonly else 'off',)]
        models = SimpleNamespace(Participant=MagicMock(), RegistrationOrder=MagicMock(), PaymentAttempt=MagicMock(), CampEnrollment=MagicMock())
        models.Participant.objects.exists.return_value = True
        modules = {'django': ModuleType('django'), 'django.db': SimpleNamespace(connection=connection),
            'django.db.migrations': ModuleType('django.db.migrations'),
            'django.db.migrations.loader': SimpleNamespace(MigrationLoader=lambda _: SimpleNamespace(
                applied_migrations=[runner.FORBIDDEN] if extra_migration else [])),
            'dic': ModuleType('dic'), 'dic.models': models,
            'dic.tutor_validation_evidence': evidence_module,
            'dic.participant_services': SimpleNamespace(eligibility=lambda _: {'eligible': True})}
        return runner, modules

    def test_default_verifier_still_rejects_a_database_with_concurrency_records(self):
        runner, modules = self.verify_context()
        with patch.dict(sys.modules, modules), self.assertRaisesRegex(RuntimeError, 'Expected no retained business fixtures'):
            runner.verify(MagicMock(), self.database, [])

    def test_explicit_final_verifier_accepts_completed_evidence_read_only(self):
        runner, modules = self.verify_context()
        helper = MagicMock()
        with patch.dict(sys.modules, modules), patch.object(evidence_module, 'capture', return_value=self.rows), redirect_stdout(io.StringIO()):
            runner.verify(helper, self.database, [], self.receipt, 'creation-hash')
        helper.verify_connection_identity.assert_called_once()

    def test_final_verifier_rejects_writes_or_phase5_before_accepting_evidence(self):
        for readonly, extra in [(False, False), (True, True)]:
            with self.subTest(readonly=readonly, extra=extra):
                runner, modules = self.verify_context(readonly, extra)
                with patch.dict(sys.modules, modules), patch.object(evidence_module, 'capture') as capture, self.assertRaises(RuntimeError):
                    runner.verify(MagicMock(), self.database, [], self.receipt, 'creation-hash')
                capture.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
