# DAWANA MEDIA STUDIO — APPROVED PRODUCT CONTRACT AND IMPLEMENTATION MAP

**Status:** Resume after DIC 2026 production population, housing and timetable release. This is a Foundation-wide product, **not** a DIC-only media-management tab. This file is a requirements contract and source audit, not authorization to activate production storage or grant permissions.

## 1. Binding decisions from the 16–17 November Media Studio conversation

1. **Dedicated, visually independent Media Studio portal:** its own workspace and route, not the existing `/dic/operations/media-management` three-card link directory and not ordinary Django Admin. Share the existing DAWANA platform, sign-in/session infrastructure, backend and private R2 storage; do not create a disconnected product or duplicate accounts.
2. **Foundation-wide, indefinitely reusable:** publish across the DAWANA Foundation public site and media archive, DIC landing pages for 2026 and future camp editions, memory/gallery destinations, and eligible Camper Portal content. **Upload once, organise by programme/campaign/event/edition, then publish to one or more destinations** without repeat uploading.
3. **One capable media operator can complete the job:** authorised media personnel can upload, enter metadata, preview, save draft, publish directly, edit, withdraw and archive. **No mandatory reviewer, dual approval chain or up-and-down authorization** for routine media work. Backend must authorize each action; owners retain high-level administration and audit oversight; operators are not blanket superusers.
4. **Rich library scope:** official flyers and promotional artwork; short promotional MP4 videos with poster/thumbnail; photos (single and bulk), captions, accessibility descriptions, organised albums/galleries; camp/programme videos (private MP4 uploads and validated YouTube/Vimeo links); lecture audio with title, lecturer, session/edition, listening and authorized download; lecturer profiles with portrait, biography, designations and appearances; activities with descriptions and photographs. Treat public foundation content and editions as first-class destinations.
5. **Premium and polished interface:** media-first previews/real thumbnails, elegant typography, sensible information density, purposeful restrained motion, balanced spacing and legible contrast (including dark mode), clear camera/microphone and other recognisable icons, compact responsive cards, excellent mobile layout, search, category/edition/status/destination filtering and bulk actions, accessible one-click publish/withdraw/archive. Avoid technical data-entry-only UI, oversized sidebar, cramped cards, inconsistent headers or clashing nested scroll.
6. **Permanent media lifecycle:** upload/save → preview → direct publish → revise/withdraw → archive, with audit receipts, safe replacement and retention policy. Archives should not be publicly delivered. No deletion or irreversible clean-up without approved retention and backup controls. Edits that change public material must not cause unwanted continued public delivery.
7. **Security and storage:** preserve two **private** production Cloudflare R2 boundaries: `dawana-production-media` for editorial files and `dawana-production-private` for participant-sensitive objects. No public bucket URLs. Django-mediated authorization for private drafts, identity-scoped recordings/participant content, downloads and delivery. Validate type, MIME/codec, file size, path/key, length, input and provider URLs; enforce copyright and lecturer/speaker permissions; protect against IDOR, guessed URLs, path traversal, oversized file and malicious uploads. Store durable objects in R2 rather than Render ephemeral disk. Only activate R2 after owner-approved credentials, provider/storage verification, backup/restore and production safety checks.
8. **Destinations and safeguards:** site public archive/gallery and landing content, DIC memories/landing and future editions, programme/lecture resources, camper streaming/download for published authorized recordings. The same stored asset can appear in multiple approved placements; a withdrawal must remove visibility everywhere that placement was published, preserving unaffected placements as explicitly intended.
9. **Operational preferences:** implement production-first with disposable/synthetic CI only; preserve current payments, housing, portal identity and DIC 2026 published timetables; no staging/demo/local DB project; no new billable Render worker. Cloudflare frontend is checked manually. Do not merge/deploy or alter production R2 without owner's explicit authorization.

## 2. Observed repository baseline (source checked on current main)

| Capability | Existing source | Gap against the approved contract |
|---|---|---|
| Staff authentication | `dawana-platform/src/services/operationsApi.js`; `backend/dic/operations_api.py` | Login/session reusable, but currently operations-themed and requires the DIC operations permission; Foundation media-only role must not be forced into other DIC functions |
| Existing media page | `dawana-platform/src/pages/MediaManagement.jsx` & CSS | Three links to Django Admin, inside Operations; **not** approved dedicated premium Media Studio |
| Editorial photos, gallery tags | `dic/memory_models.py`, `memory_admin.py`, `memory_views.py` | Camp-edition scoped; not unified cross-Foundation catalogue or bulk upload; distinct change/publication permissions |
| Videos | `dic/memory_models.py`, video provider services | Uploaded clips and hosted video validation supported in model; unified listing/placements/Studio actions missing |
| Flyers/promotional MP4 | `dic/promo_models.py`, `promo_admin.py` | Strict edition-specific limits (1 official published flyer, 3 prior-experience + 2 intro promo videos), no generic Foundation placement model |
| Lecturer/activity records | `dic/showcase_models.py`, related admins/views | Edition appearances require separate verification evidence; direct media publication should not bypass factual speaker-participation verification |
| Lecture recordings | `dic/camp_release_models.py`, `camp_release_admin.py`, `camp_release_api.py` | File/media delivery exists; unified media library, compact metadata flows and destinations missing |
| User groups | `dic/staff_roles.py` | Current `DIC Media Editors` and `DIC Media Publishers` are distinct role groups. Add a **single least-privilege unified Studio operator role**, without escalating old group members or removing audit |
| Secure storage | `dic/storage_configuration.py`, `memory_storage.py`, `recording_storage.py` | Two-bucket validation exists; actual production configuration/activation and backup/restore readiness must be checked, never inferred |
| General placement catalogue | No reusable Foundation-wide media asset/destination model located in audited source | Needed for uploads reused across website, programmes, editions, archives and Camper Portal |
| Studio management API | Existing DIC-specific views and admin models | Need authenticated permissioned listing/search/filters, creation/upload, multi-destination publish/unpublish, safe bulk actions, metadata update and audited archive endpoints |

**Do not mistake tests on existing DIC-specific models for full Media Studio acceptance.** Do not remove or weaken old media publisher permissions; route each new workflow through existing authorization, audit and delivery constraints.

## 3. Intended architecture and staged delivery inside one milestone

### A. Foundation media catalogue and destinations
- Build a reusable editorial asset record with unique stable key, type, title, caption/description/alt text, creator, timestamps, provenance/consent and media location metadata. Associate optional edition, programme, campaign, event, lecturer, session and gallery/album.
- Model per-destination placements with draft/published/withdrawn/archived states; enforce destination-specific limits (official DIC flyer and promo slots), audience authorization, and edition requirements. Reuse one object file; no public raw R2 URL or automatic redistribution of private participant media.
- Existing legacy DIC models remain valid. Use additive migration and source-compatible adapters; never silently convert/delete existing records. No migration/apply in normal web build/start.

### B. Media Studio service and permissions
- Shared authenticated staff session, separate Studio authorization: Studio reader/editor/publisher scopes; unified media operator gets create/edit/publish/withdraw/archive capabilities without a second reviewer. Supervisory tasks (storage activation, credentials, destructive retention, role grants) remain owner-only.
- All operations server-enforced, CSRF/session-safe, no web storage access from the client. A draft preview must require staff view permission; published public content may be delivered through existing controlled publication routes; Camper Portal download requires participant entitlement.
- Audit media upload, metadata change, publication, withdrawal, destination change, archive, and backup-safe deletion, with user, asset, placement and prior/new state.
- Protect and test source reference, ID, edition/audience boundary, duplicate uploads, accepted codecs, maximum sizes, XSS, unsafe external URLs and partial bulk failures.

### C. Polished dedicated interface
- Dedicated `/media-studio` route with its own branded, responsive navigation and sign-in experience using shared auth. Overview dashboard, upload composer (bulk photo support), visual library grids, file type tabs, fast filters/search, details drawer/editor, destination chooser and publication controls.
- Section cards: Flyers & artwork; Promotions; Photography & galleries; Videos & external embeds; Lecture audio; Lecturers; Activities; Archive. Include thumbnails, state, media type, publication destinations and source programme/edition.
- Explicitly show storage-not-configured states; do not expose fake working upload or publish buttons. Subtle loading, empty, error/retry states; dark mode; accessible labels and keyboard navigation; no Camera/Mic ambiguity.

### D. Acceptance and production activation
- Test each asset type from valid and invalid upload to authenticated preview, publish at correct public/private destination, withdraw/archive and re-check after revocation.
- Test responsive mobile, dark mode, no layout overflow, bulk uploads, search, cross-edition reuse, destination-specific publication limits, current and archived dates, lecturer verification boundary.
- Keep payments, check-in, housing, 180 published DIC timetable entries, enrolment access and private camper media unaffected.
- Confirm backend R2 credentials and bucket setup **without exposing secret values**, verify ownership/backups/restoration, activate only by explicit owner action and release deploy with clean relevant CI. Cloudflare frontend verified manually after merge/deploy.

## 4. Never silently reintroduce rejected designs
- Not a DIC-only or Operations sidebar media links page.
- No compulsory multiple-person editorial approval queue or reviewer/publisher chain.
- No broad staff superuser accounts as a substitute for scoped permission.
- No public R2 links or direct unauthenticated private draft/lecture downloads.
- No presumed production R2 activation, automatic data deletion or local/staging detour.
- No duplicate media upload to reach multiple destinations.
- No invented content, speaker verification, captions, external videos or media programme associations.

## 5. Current milestone progress
This contract records approved decisions, existing reusable code and missing components; the full Media Studio portal, service, asset-placement model, and production R2 cutover are **not yet implemented** merely by adding this file. Actual code commits and verification are tracked separately.
