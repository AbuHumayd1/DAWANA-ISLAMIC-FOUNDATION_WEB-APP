# DIC 2026 premium badge concepts — awaiting review

Production portrait rendering is UNCHANGED. Neither candidate is connected to an
API, template selector, dashboard, issuance service or database. Selection and
visual approval are required before any production adoption. No Stage 2 work.

## Two distinct concepts

**A — Classic Executive:** symmetrical deep-green header, original official logo
on a cream medallion with fine gold outline, restrained eight-point geometric
details, formal serif participant name, double-detail photo treatment and an inset
house ribbon. The house colour frames a cream label for dependable contrast.

**B — Modern Premium:** asymmetrical header with the original logo in a light
rounded tile, left-aligned branding and name, geometric corner detail, larger photo
treatment, separate white verification panel and a taller house section with a
prominent colour rail. Lettering sits on a light inset so pale house colours remain
readable. These are distinct compositions, not just colour variants.

Both retain the continuous 3 mm green edge, an inset gold keyline, original logo
pixels without recolouring, black-on-white QR with four-module quiet zone, and
the exact supplied verification URL. Name wrapping has an 11 pt minimum; exceptional
names that cannot fit trigger explicit review instead of truncation or tiny text.
ID and house sections follow the measured name height to avoid excessive gaps.
House values are explicit synthetic fixture configuration in these previews;
there are no invented official house names or colours. Pending/unconfigured house
colour uses a neutral treatment. Photo rasters retain aspect ratio and face content.

## Physical layout

ReportLab only. Exactly 90 x 130 mm portrait. A4 is 210 x 297 mm, two columns/two
rows, 6 mm gaps, 12 mm side margins and 15.5 mm top/bottom margins. External corner
guides run 1–2.5 mm outside each card. No rotation or page scaling is used.
Seventeen badges occupy five pages, with one badge on the final page.
The QR squares are 34 mm (Classic) and 33 mm (Modern), including quiet zones.

## Generate both concepts locally — no database

Codex could inspect the prior PNGs, but Python execution is still denied access
to the configured base interpreter. No premium PDFs/PNGs have been generated in
Codex; no runtime/visual success is claimed. Use the existing activated PowerShell:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
python -B scripts\generate_premium_badge_previews.py
python -B backend\manage.py test dic.test_premium_badge_concepts.PremiumBadgeConceptTests --verbosity 2
```

The standalone generator configures `DATABASES={}` and never loads .env or Django
apps/models. It neither connects to a database nor invokes credentials or audit
services. QR payloads are explicitly invalid synthetic URLs under example.invalid.
The portrait is a synthetic raster illustration, not a real participant photo.
The tests use SimpleTestCase and cannot access a database. Existing production and
requirements-test-ids.txt packages suffice; no new dependencies are added.

## Exact intended output paths

All paths below are relative to the repository root. They are intended output
paths until the command succeeds, not claims that files already exist.

- output/pdf/dic-premium-concepts/classic-executive-single.pdf
- output/pdf/dic-premium-concepts/classic-executive-four-up.pdf
- output/pdf/dic-premium-concepts/classic-executive-assigned-house.pdf
- output/pdf/dic-premium-concepts/classic-executive-pending-house.pdf
- output/pdf/dic-premium-concepts/classic-executive-long-name-photo.pdf
- output/pdf/dic-premium-concepts/classic-executive-batch-17-five-pages.pdf
- output/pdf/dic-premium-concepts/modern-premium-single.pdf
- output/pdf/dic-premium-concepts/modern-premium-four-up.pdf
- output/pdf/dic-premium-concepts/modern-premium-assigned-house.pdf
- output/pdf/dic-premium-concepts/modern-premium-pending-house.pdf
- output/pdf/dic-premium-concepts/modern-premium-long-name-photo.pdf
- output/pdf/dic-premium-concepts/modern-premium-batch-17-five-pages.pdf

Each PDF page produces `<pdf-stem>-page-N.png`; each single-card scenario also
produces `<pdf-stem>-badge.png`. The folder also contains `concept-comparison.png`,
`index.html` and `verification.json`. Open index.html for review of both concepts.
The manifest is marked INCOMPLETE before generation and only marked passed after
all checks succeed; visual approval remains PENDING even after automated success.

## Verification and acceptance

### Long-name layout correction

The original failing test supplies the exact 165-character value
`'SYNTHETIC ' + ('Abdulrahman Olayiwola Muhammad ' * 5)`, including a trailing
space. The reported 18 pt failure occurs in Classic Executive, the first iteration.
Inspection of the installed Georgia Bold and Arial Bold TrueType advance metrics
and the ReportLab wrapping/leading source shows that BOTH concepts need six lines
at their 11 pt minimum: 26.077 mm, exceeding the original 23 mm block. Modern's
iteration was not reached by the failing original test; its equivalent overflow
was confirmed by the font-metric calculation, not a Python test run.

The name region is now 76 x 28 mm at (7,76) mm within the badge. Half-millimetre
insets leave 75 x 27 mm for text; the 11 pt readability floor is unchanged.
The verification panel loses only surplus bottom padding (QR pixels, size, payload
and quiet zone are untouched), ending at 75 mm. Number label/ID spacing is tightened
and the ribbon follows measured text height. The ribbon still ends by 124 mm and
retains at least 9 mm height. Space shrinking is disabled so wrapping respects the
actual available width. No clipping, truncation or hidden overflow is used.

Using the installed Windows font advances, the corrected original fixture fits
Classic at 11 pt / 26.077 mm and Modern at 11.25 pt / 26.670 mm. This independent
Node calculation passed; ReportLab/PyMuPDF execution remains blocked by Python
access denial, so actual PDF acceptance is NOT inferred from it.

The original pagination/name test and QR-scanning test are retained. A new matrix
uses subtests for short, original long, multiple-word and unusually long unbroken
names in BOTH concepts. It checks full-page extracted glyph bounds, character
preservation, minimum font size and separation from number/QR/house sections.
The preview generator now uses the exact failing long name and checks glyph bounds
and complete name text on every rendered badge. Existing preview files predate this
fix until regenerated; no new PDFs were rendered in Codex.

Files changed for this correction: `backend/dic/premium_badge_concepts.py`,
`backend/dic/test_premium_badge_concepts.py`,
`scripts/generate_premium_badge_previews.py`, and this report.

Run from the existing activated PowerShell, repository root (no databases):

```powershell
python -B backend\manage.py test dic.test_premium_badge_concepts.PremiumBadgeConceptTests --verbosity 2
python -B scripts\generate_premium_badge_previews.py
```

The generator checks actual PDF page size/rotation, exact card bounds/placement,
pagination, each cutting-guide coordinate, green edge pixels, configured/neutral
house accent placement and QR decoding for every badge on every page. Unit tests
also cover synthetic-only isolation and readable long-name rendering.
These are implemented checks, NOT claims of execution here.

Executed in Codex: inspected the previous four-up PNG, checked A4 placement/page
count arithmetic, and ran git diff --check successfully. Attempted premium
generation stopped at the interpreter access denial. Python unit tests, generated
PDF geometry/QR checks and visual inspection of premium output were not executed.

Review actual rendered PNGs and PDFs for logo contrast, names, photo/QR balance,
ornament restraint, house prominence and long-name fit. Test physical actual-size
prints, lamination/holder fit and camera scanning before approval. Return a concept
selection and any requested refinements; neither concept will replace production
without that selection.

## Files added for this request

- backend/dic/premium_badge_concepts.py — review-only ReportLab candidates.
- backend/dic/test_premium_badge_concepts.py — database-free candidate regressions.
- scripts/generate_premium_badge_previews.py — twelve PDFs, PNGs and comparison.
- backend/PREMIUM_BADGE_CONCEPTS.md — this report.

No existing source file, database model, migration, production portrait/PVC/A6
renderer, permission, payment, issuance or audit path was modified for this request.
