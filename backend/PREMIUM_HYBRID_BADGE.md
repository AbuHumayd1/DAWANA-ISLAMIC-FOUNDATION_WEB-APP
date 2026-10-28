# Final Premium Hybrid — third preview candidate

Status: preview renderer, seven-scenario generator and seven database-free tests are
implemented. Python cannot execute in Codex (access denied to the venv's configured
base interpreter). No hybrid PDF/PNG has been generated here, and visual approval
is NOT claimed. Production and both earlier concepts remain untouched.

## Cohesive hybrid design

Modern Premium supplies the deep-green header, original logo on a cream tile,
strong sans-serif participant name, side-by-side photo/QR and cream body. The
large triangle is removed entirely. Classic-inspired refinements are a fine gold
inner keyline, full thin gold header rule, thin gold inset photo detail, consistent
small radii and compact inset house ribbon. The original logo pixels are not changed.

Badge dimensions remain exactly 90 x 130 mm with a continuous 3 mm green edge.
A4 remains 210 x 297 mm, four-up, 6 mm gaps, 12 mm side and 15.5 mm top/bottom
margins, original external cut-guide coordinates and partial-page positioning.
Photo rasters retain aspect ratio and face content. The original Modern QR square
at (49,37) mm remains 33 mm, black on white with four-module quiet zone. The helper
encodes the supplied verification URL verbatim; it does not generate credentials.

The house ribbon is 9–12 mm high, follows the number immediately, and uses a
coloured outer band with a light text inset. There is no large empty outline.
House colour is an explicit resolved `house_colour` context value, corresponding
to House.badge_colour in a future approved integration; this preview has no model
imports or production hook. Synthetic fixture values are labelled synthetic.
Missing/pending colour uses the shared neutral treatment and existing pending text.
The ribbon cannot cover the green edge. The lower content group is centered in
the available body area for short names and uses the full area for long names.

## Intelligent name layout

The hybrid has its own layout planner; the old concepts' algorithms are unchanged.
It measures real PremiumBold glyph advances and:

- Prefers a single line for ordinary names at 16–19 pt when the entire name fits.
- Otherwise balances natural word-boundary breaks using dynamic programming,
  with strong penalties for a very short or numeric last line when avoidable.
- Splits only words wider than the line, keeping combining marks with their base.
- Uses up to the 75 x 27 mm text area within a padded 76 x 28 mm name region.
- Preserves the 11 pt minimum and all name characters; never clips or truncates.
- Measures explicit ReportLab line breaks again before drawing, then positions the
  number label, number and ribbon using the actual text height.

Exceptional input beyond the readable capacity causes an explicit review error
instead of hidden overflow. The exact 165-character regression name is retained:
`'SYNTHETIC ' + ('Abdulrahman Olayiwola Muhammad ' * 5)`.

## Run locally without a database

From the existing activated PowerShell environment, repository root:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
python -B backend\manage.py test dic.test_premium_hybrid_badge.PremiumHybridBadgeTests dic.test_premium_badge_concepts.PremiumBadgeConceptTests --verbosity 2
python -B scripts\generate_hybrid_badge_previews.py
```

Both test classes use SimpleTestCase: no test database is created. The standalone
generator uses `DATABASES={}` and never loads .env, Django apps or models. No
issuance, payment, authentication, verification service or audit operation occurs.
It reuses synthetic factory/verification helpers and the old concepts' read-only
drawing helpers, without editing them. All QR URLs use example.invalid and are
explicitly invalid synthetic credentials. Existing test dependencies suffice.

## Exact intended output files

These are INTENDED output paths, not claims of files generated in Codex:

- output/pdf/dic-premium-hybrid/hybrid-assigned-house.pdf
- output/pdf/dic-premium-hybrid/hybrid-housing-pending.pdf
- output/pdf/dic-premium-hybrid/hybrid-with-photograph.pdf
- output/pdf/dic-premium-hybrid/hybrid-without-photograph.pdf
- output/pdf/dic-premium-hybrid/hybrid-exceptionally-long-name.pdf
- output/pdf/dic-premium-hybrid/hybrid-four-up.pdf
- output/pdf/dic-premium-hybrid/hybrid-batch-17-five-pages.pdf

Each page also produces `<pdf-stem>-page-N.png`; singles additionally produce
`<pdf-stem>-badge.png`. The same folder contains `three-concept-comparison.png`,
`comparison-classic-executive.png`, `comparison-modern-premium.png`,
`comparison-hybrid.png`, `index.html`, and `verification.json`.
Comparison renders are written ONLY into this new folder, never over the earlier
concept artifacts. The portrait illustration is synthetic, not a real photo.

The manifest starts as INCOMPLETE and becomes passed only after the actual PDF
geometry, cut-guide coordinates, name preservation/bounds, frame/accent colours and
every QR decode succeed. Visual approval remains PENDING regardless of automation.
Metadata records measured name lines/size and section positions for review.

## Tests and safeguards

Seven new tests cover readable ordinary single-line names, avoidance of a lone 01,
long/multiword/165-character and oversized-word names, actual PDF text bounds and
section separation, exact dimensions, 1/4/17 pagination, cut-guide counts,
configured/neutral ribbon pixels and frame, missing photographs, supplied raster
photograph containment/aspect ratio, QR scanning,
synthetic-only gating, and pixel-identical earlier concept rendering before/after
the hybrid call. Existing concept regression tests are retained unchanged.

Actually executed in Codex: Python probe/test attempt (blocked before startup),
source/route isolation review, whitespace check, and source hashes confirming the
existing concept and production portrait files remain unchanged. An independent
Node read of Arial Bold's TrueType advances confirmed that `SYNTHETIC Participant
01` fits one line at 17 pt in 74.983 mm of the 75 mm text width. This is a font-metric
check, not PDF execution or visual approval. Backend tests,
actual hybrid PDF checks and visual review are UNEXECUTED here.

## Files added

- backend/dic/premium_hybrid_badge.py
- backend/dic/test_premium_hybrid_badge.py
- scripts/generate_hybrid_badge_previews.py
- backend/PREMIUM_HYBRID_BADGE.md

No existing source file is modified for this request. There are no model,
migration, database, real participant, credential, permission, authentication,
payment, print-history, production-renderer or legacy-format changes.

Stop at preview review. Approve the hybrid visually before any production wiring.
