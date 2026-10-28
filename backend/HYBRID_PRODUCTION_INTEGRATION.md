# Approved premium hybrid production integration

The user approved the hybrid visually and reported 11 local concept tests passing.
The approved drawing is now the default behind the existing portrait `render_pdf`
function. No API, frontend, migration or model change is required.

## Production path

Existing unchanged callers:
- PrintingExportView: authorized Operations bulk PDF, existing export audit and
  batch/version snapshot, deduplication, locking and cache headers.
- identity_views.card_view: authorized staff individual `?format=portrait` PDF.
- participant_api.PortalCardView: existing scoped participant/guardian portrait PDF.

All still resolve active eligible credentials through card_context and call
portrait_pdf.render_pdf. That function now resolves house name/colour through the
existing validated housing helper, overrides any supplied house context, and calls
the shared approved hybrid drawing. The original synthetic-only preview wrapper
still rejects ordinary participant contexts. Production drawing omits the synthetic
footer unless an explicit synthetic fixture flag is present. No rendering code
issues, rotates, revokes or writes credentials or participant records.

The hybrid visual composition and dimensions are unchanged: 90 x 130 mm, four-up
A4 portrait, 6 mm gaps, 12/15.5 mm margins and external cutting guides. House colour
uses House.badge_colour; missing/pending assignment uses the approved neutral.
Assigned houses without configured colour retain their name with neutral accent.
Existing PVC and A6 template branches remain untouched. The original premium
concepts remain intact for comparison. Missing PDF dependencies retain the existing
503 response handling; the official logo remains required by the approved design.

## Files changed

- backend/dic/portrait_pdf.py: replace superseded body with hybrid context adapter.
- backend/dic/premium_hybrid_badge.py: shared internal drawing, retain synthetic
  preview guard, conditional synthetic footer and production PDF title.
- backend/dic/test_hybrid_integration.py (new): database-free integration checks.
- scripts/generate_portrait_previews.py: align existing production-path fixture
  verification with approved QR bounds and dynamic compact ribbon placement.
- backend/HYBRID_PRODUCTION_INTEGRATION.md (this report).

New tests compare rasterized production output against approved preview output,
verify server-resolved house overrides, absent production watermark, exact supplied
QR decoding, pending-house text, photograph containment/aspect ratio and complete
165-character name preservation. Existing hybrid, portrait, cache, identity/audit,
permissions/CSRF, credential reuse and legacy PVC/A6 tests remain in place.

## Verification

Python still reports access denied to the configured base interpreter in Codex.
Database-free tests were attempted but did not start. No new backend runtime pass
is claimed. Whitespace/source review completed; database suites were not invoked.
No database connection, migration, test database creation, real credential issuance
or participant/payment mutation occurred. No frontend or Stage 2 changes.

Run database-free tests first from the existing activated PowerShell:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
python -B backend\manage.py test dic.test_hybrid_integration dic.test_premium_hybrid_badge dic.test_premium_badge_concepts dic.test_portrait_design dic.test_printing_cache --verbosity 2
python -B scripts\generate_portrait_previews.py
```

The test classes are SimpleTestCase and forbid DB access. The generator configures
DATABASES={} and writes synthetic production-path PDF/PNG fixtures to
output/pdf/dic-portrait-stage1/. It cannot issue credentials or access models;
its fixture house provider is explicitly substituted for database housing lookups.

Only AFTER explicit approval to create isolated test databases and apply test schema:

```powershell
python -B scripts\validate_dic_backend.py --ids-only
python -B scripts\validate_dic_backend.py --phase2-and3
```

Those existing guarded suites cover permissions, CSRF, active issued eligibility,
print audits/history, QR reuse/verification and individual/guardian/legacy formats.
They create and retain isolated databases; they were NOT executed for this task.
No development migration command is part of this integration.

Pending: local execution of the integration tests, refreshed synthetic PDFs and
authorized end-to-end download/export verification in an approved isolated setup.
