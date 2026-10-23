# DIC landing refinements — staging development

Branch: staging/dic-page-refinements, based on approved integration 3520770.
Workspace: the existing clean integration checkout in the temporary directory.
The original dirty Desktop checkout is untouched. Production release branch
release/production-launch-20261023 remains at 424ccf7; no production merge,
push, deployment, remote migration or R2 operation was performed.

## What changed
- DICCampInfo replaces the tall information panel with a two-column fact grid,
  compact status, dynamic dates/venue/deadline/fee range, primary registration
  button and existing payment-return/status link. Detailed category names and
  early-bird information remain in the existing registration form. The hero
  no longer exposes configuration counts, internal category lists or missing-
  configuration wording. Prices are read from the backend, never hardcoded.
- DICEditorial displays the official flyer with an accessible native enlargement
  dialog and registration CTA, up to three experience MP4s and two introduction
  MP4s. Videos load their source only after the visitor selects Play; posters
  are lazy-loaded and native controls support inline mobile playback. No public
  search, dropdowns or video archive controls are introduced.
- PromoVideo and CampFlyer reuse ModeratedShowcase publication state, actor,
  timestamp and separate publish permissions. Admin edits return published
  assets to review, publish/withdraw actions are permission checked and audited,
  previews require staff view permission, and assets are never automatically
  deleted. Each promo targets the active landing edition; experiences identify
  an earlier source edition. Publication counts are locked per target edition.
  One flyer may be published per edition (database constraint).
- The landing photo component uses ?curated=1: only published FEATURED images,
  at most six. Existing full-gallery behavior/API remains available elsewhere.
- Existing CampActivity content has coloured cards, decorative icons, short
  visible descriptions and reduced-motion-aware animations. Upcoming activity
  and lecturer queries now follow the active edition instead of hardcoding 2026.
  No activities, programme schedules, posters, videos or flyer content are seeded.
- Media.jsx, hosted-video provider/API/components, payment handling, pricing and
  registration business rules are not changed from this branch's integration base.
  Existing hosted lecture videos are no longer presented as DIC promotional clips.

## Backend and migration inventory
New: promo_models.py, promo_storage.py, promo_views.py, promo_admin.py,
test_promotions.py, migrations/0021_promovideo_campflyer.py.
Wiring: dic/models.py, dic/admin.py, dic/urls.py, config/settings/base.py.
Existing content queries: memory_views.py and showcase_views.py.

Apply ONLY after staging approval, backup and migration review:
    python manage.py makemigrations --check --dry-run
    python manage.py migrate --plan
    python manage.py migrate
0021 depends on existing DIC 0020. It adds two editorial tables and one conditional
flyer uniqueness constraint; no participant/payment tables or records are changed.
Do not skip the earlier integration migrations 0018-0020 if staging lacks them.
The migration is prepared manually because local Python cannot execute; confirm
model/migration parity in the trusted staging validation runtime before applying.

## Configuration before staging deployment
Keep the existing private R2 configuration:
DIC_MEMORY_STORAGE=s3
DIC_MEMORY_S3_BUCKET=dawana-staging-media
DIC_MEMORY_S3_ENDPOINT=<staging account HTTPS S3 API endpoint>
DIC_MEMORY_S3_REGION=auto
AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY securely injected on the backend only.
Never expose a public r2.dev endpoint, bucket URL or presigned object URL.
No extra bucket, queue, worker, video CDN or recurring paid service is introduced.
Serving video through the existing backend consumes its existing bandwidth/compute;
check the hosting plan's upload size, request timeout and egress limits before use.

Install a trusted ffprobe binary on the SAME backend host and ensure it is on PATH,
or set DIC_FFPROBE_BINARY to its executable path. This is a local executable, not
a remote transcoding service. It may require a reviewed runtime/build-image change;
do not silently change production hosting to install it. If unavailable, uploads
fail closed with an admin validation message. No new Python package is required.

MP4 policy: genuine MP4 container, H.264 video, optional AAC audio, maximum 100 MiB
and three minutes. ffprobe forces the MOV/MP4 demuxer, disables external data
references, allows only local-file protocol and has a 20-second timeout. This is
container/codec validation, not a video transcoder or malware scanner. Editors
must export browser-compatible MP4s (fast-start recommended), with consent reviewed.
File names are generated, ContentType is video/mp4, and R2 PUT uses IfNoneMatch='*'
with no overwrite fallback. The installed boto3/botocore must support that field.
Posters and flyer images reuse JPEG normalization/metadata stripping (2400px maximum).
There is no automatic video metadata stripping/transcoding; don't upload sensitive
source videos. Video metadata removal was not part of this refinement's requirement.

Public asset routes perform publication checks before opening storage. Video GET
supports bounded streaming and a single byte range (including suffix/open-ended),
HEAD avoids fetching the video body; invalid ranges return 416. Responses are
private/no-store and nosniff. R2 URLs/keys are not returned to clients. Withdrawal
blocks subsequent requests, but cannot retract bytes already delivered/downloaded.

Verify the current staging API proxy forwards GET/HEAD, Range, Content-Range and
Accept-Ranges without buffering/caching videos or rewriting 206 responses. No
bucket CORS change is required when playback uses the existing same-origin API.
Don't deploy until an actual mobile browser can start and seek the synthetic clip
through the existing Netlify-to-Render proxy within the hosting timeout limits.

## Admin preparation (no content/data changes were performed here)
- Give editors standard add/change/view permissions on PromoVideo/CampFlyer.
- Give only designated publishers publish_promovideo and publish_campflyer.
- Upload the approved poster, H.264 MP4 and alt text; use Draft/Ready for review.
- Publish at most 3 experience and 2 introduction clips for the active edition.
  Publishing additional clips is rejected. Withdraw an old clip to replace it.
- Upload an approved official flyer image and alt text; withdraw the current
  flyer before publishing its replacement. Registration CTA follows backend status.
- Mark at most the desired six approved CampPhotographs featured; the landing
  page will not fall back to uncurated archive images.
- Enter only committee-approved activities for the active edition and publish them.
- Deactivate QA-only registration categories using the EXISTING is_active flag.
  No production/staging category records were inspected or edited here. The public
  API already returns active categories only; no name-based guessing/filtering or
  registration pricing change was added to hide accidentally active test records.
  Check that the active edition contains only approved real registration categories
  before exposing the page. Hero category names have been removed regardless.

## Validation performed / still required
Passed: 12 Node checks for fee/date presentation, pricing, API bearer/session retry
behavior and payment-return handling. git diff --check passed.
Blocked: Python backend tests cannot start (local interpreter Access denied).
Frontend dependency installation failed because the npm cache is inaccessible;
Vite/browser build/visual checks remain unverified. No remote test was attempted.
Backend tests added cover draft asset privacy, publication caps, withdrawal,
MP4 validation, create-only writes, range parsing, HEAD behavior and bounded streams.

In an approved trusted environment, with an isolated PostgreSQL TEST database:
    python manage.py test dic.test_promotions dic.test_memories dic.test_videos dic.test_showcase dic.tests.RegistrationApiTests dic.tests.PaymentApiTests
Frontend:
    npm ci
    npm test
    npm run lint
    npm run build
Then validate mobile at 320/375/768px and desktop: no horizontal overflow, natural
hero stacking, flyer enlargement/close/Escape/focus/scroll restoration, reduced
motion, video poster click/play/seek/HEAD/range behavior and draft/withdrawn URLs.
Use synthetic assets, never participant footage, for initial staging checks.
No regression test/build pass or visual approval is claimed beyond the checks above.
