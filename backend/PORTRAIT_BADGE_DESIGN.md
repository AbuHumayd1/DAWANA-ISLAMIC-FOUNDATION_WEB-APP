# DIC portrait badge design correction

Status: production renderer and database-free fixture generator updated; PDFs
have NOT been generated in Codex because its Python launcher cannot access the
configured base interpreter. No visual approval is claimed.

## Root cause

`batch-17-copies-three-pages.html` came from
`IdentityCardTests.test_a4_page_groups_cover_partial_and_multiple_pages_without_empty_pages`.
It calls `render_cards(..., batch=True)` without a card_format, selecting the
legacy `pvc` default in identity_views, then `dic/identity_cards.html` with its
85.6 x 54 mm rules and eight-card pagination. Thus 17 PVC cards occupy three pages.
This was the WRONG acceptance fixture for the portrait feature, not a CSS bug in
the portrait export. Neither the portrait PDF renderer nor the Operations PDF
export uses that HTML template. The test's artifact is now explicitly named
`legacy-pvc-batch-17-three-pages.html`; its PVC assertions and layout are unchanged.
The new portrait fixture uses the production renderer directly. Seventeen portrait
badges correctly occupy FIVE pages (4+4+4+4+1), not three.

## Portrait composition

Exactly 90 x 130 mm; unsupported configured dimensions fail rather than shrink or
rotate. Four-up A4 portrait is 210 x 297 mm, with 12 mm horizontal and 15.5 mm
vertical margins, 6 mm gaps, and external 1–2.5 mm corner guides. No page scaling.
Badge origins from the page's top left are (12,15.5), (108,15.5), (12,151.5),
(108,151.5) mm. Outer frames are solid Dawana green with a continuous 3 mm edge.
The cream inner body, green header, cached official logo, gold rule/photo frame,
dedicated photograph box, white square QR, centered name/ID, and inset house panel
form a separate vertical composition; no PVC CSS or template is reused.

House accents come only from validated `House.badge_colour`. Missing/unapproved
colour is returned as None; its generic neutral panel is not a house assignment.
Pending housing is explicitly labelled. The accent panel is inset 6 mm and never
covers the brand edge. A white text inset preserves contrast for arbitrary
configured colours. Portraits preserve aspect ratio. QR payload, correction level
and four-module quiet zone remain unchanged; the square is now 38 mm.

## Fresh synthetic previews (database-free)

From the existing activated PowerShell environment, repository root:

```powershell
python -B scripts\generate_portrait_previews.py
python -B backend\manage.py test dic.test_portrait_design.PortraitDesignTests --verbosity 2
```

The generator configures minimal Django settings with `DATABASES={}` and does not
load .env, initialize Django apps, import models, connect to a database, invoke
issuance or create credentials. House data and portrait illustration are explicitly
synthetic. QR payloads use example.invalid and are not valid credentials. It calls
the SAME production `render_pdf` function with an isolated fixture house provider.
No independent HTML/CSS imitation of the badge design is used.

With production and `requirements-test-ids.txt` dependencies installed, it writes:

- output/pdf/dic-portrait-stage1/portrait-single.pdf
- output/pdf/dic-portrait-stage1/portrait-four-up.pdf
- output/pdf/dic-portrait-stage1/portrait-configured-house.pdf
- output/pdf/dic-portrait-stage1/portrait-pending-house.pdf
- output/pdf/dic-portrait-stage1/portrait-long-name-photo.pdf
- output/pdf/dic-portrait-stage1/portrait-batch-17-five-pages.pdf

Each PDF page also has a PNG. `index.html` is a gallery of those actual PDF renders.
`verification.json` records page count, actual badge bounding boxes, cut-line
checks, frame/accent pixel checks and decoded QR counts. The generator fails if
the cached logo is missing, geometry differs, guides are misplaced, the green edge
is lost, a configured colour renders incorrectly, or any cropped QR cannot decode.
The long-name fixture uses a raster synthetic portrait illustration, not a real
participant photograph. Its photo-box fit must also be reviewed with approved
photographs during final acceptance.

These paths are intended outputs, NOT claims that artifacts currently exist.
Review resulting PNGs/PDFs before visual approval; automated success is not design
approval. Print at actual size / 100% and physically measure holder fit and QR scans.

## Files changed

- backend/dic/portrait_pdf.py: exact geometry, vertical visual design, inset house
  accent, neutral missing-colour semantics; lazy housing imports allow DB-free QA.
- backend/dic/test_identity_cards.py: unambiguous legacy PVC fixture filename only.
- backend/dic/test_id_printing.py: neutral-colour expectations and missing-colour case.
- backend/dic/test_portrait_design.py (new): database-free geometry/frame regressions.
- scripts/generate_portrait_previews.py (new): six production-rendered synthetic
  PDFs, raster previews and geometric/QR verification without database access.
- backend/PORTRAIT_BADGE_DESIGN.md (this report).

No legacy PVC/A6 renderer, issuance/payment/QR-verification service, permissions,
CSRF check, print API, audit model or migration was changed for this design task.
