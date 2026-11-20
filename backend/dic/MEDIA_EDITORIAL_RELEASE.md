# DAWANA Media & Publications — release contract

This branch expands the existing Media Studio; it is NOT a new staff portal.
Preserve existing staff sessions, approval permissions, protected camper-only
media and production hosting. No worker, Docker service, staging database or
unapproved external subscription account is required to review this code.

## Public features

- Six original media categories continue working. Media Studio can create
  additional named lecture/programme collections and podcast shows without a
  frontend redeployment. Media staff can assign public legacy video/audio
  library records to those collection slugs.
- Dedicated podcast episodes have a show, season, episode and a validated
  YouTube/Vimeo URL. The website embeds those players where providers permit.
- Live programmes have optional YouTube viewing and Google Meet joining URLs.
  Google Meet meetings are *not* embedded as interactive meetings. Approved
  broadcasters can advance a live item through scheduled/live/ended without
  republishing or creating multiple alerts.
- Publications include approved articles, PDFs and event notices. Uploaded PDF
  files use the existing private media storage, cap at 15 MB, validate PDF
  signature and are served only as explicit approved, download-only responses.
- The homepage public Media API never serves more than three featured media
  assets, irrespective of staff publishing count; the Media page has no such
  homepage limit.
- Redundant 'published by the Foundation team' or 'Official publications'
  language is removed from the selected public sections.

## Access and publication

- Only existing Media Studio catalogue managers may create/edit collections
  or draft content. Only authorized placement publishers may make a collection
  publicly visible or publish/withdraw content. Existing legacy media checks
  remain in force.
- Private drafts and unpublished collections are not served by public APIs.
  Editing a published item requires withdrawing it first. Audit events record
  publication and collection changes. Staff publication is a deliberate action,
  not implied by uploading a file.
- Articles display as escaped plain text (not untrusted HTML/JS).
- The new public routes never accept an external embed string as executable
  HTML; video embeds are approved by the server's provider allowlist.
- Do not grant media roles authority over DIC finance or camper records.

## Optional website push subscriptions

Configure OneSignal's verified web site origin and service worker first.
Set the following **on Render** as secret environment variables when ready:

- `DAWANA_ONESIGNAL_APP_ID` — public OneSignal web app identifier.
- `DAWANA_ONESIGNAL_API_KEY` — OneSignal REST API key (NEVER in frontend).

The public client fetches only the app ID (never the API key). The official
OneSignal Web SDK loads without asking permission. The browser permission
request occurs ONLY after the visitor deliberately clicks Enable notifications.
The SDK worker is available at `/OneSignalSDKWorker.js` on Cloudflare.
The visitor can revoke consent through browser settings. On iOS, web push
requires a Home Screen-installed site; a normal browser tab is insufficient.

Newly approved public editorial publications and legacy media archive
placements trigger a bounded, optional OneSignal API request to opted-in
subscribers. It uses a deterministic provider idempotency key for each
publication event to guard retries and never blocks the publication from
succeeding when the provider is unavailable. The editorial interface can
explicitly retry an unsent alert. If OneSignal is not configured, subscriptions
and sending are disabled, not simulated.

This release does not create email newsletters or a paid membership system.
Notifications are site-wide; topic-specific preferences are not implemented.

## Production migration requirements

Migration `dic.0047_studio_publications` adds only
`dic_studiocollection` and `dic_studiopublication`, with no backfill
and no edits to payment or registration rows.

This branch must NOT be deployed to production as a normal build before 0047
is applied. Follow DAWANA's protected release workflow: verify current
production DB identity and exact migration plan, take a fresh readable
production backup, run the owner-approved one-time non-promoting guarded
migration, verify tables/constraints, clear one-time approval variables, and
then deploy the normal build. Do not reuse the 0046 approval token for 0047.

After deployment, test draft invisibility, publication/withdrawal,
collection navigation, actual PDF download, YouTube embedding and Meet
joining, and then perform OneSignal end-to-end delivery tests *after*
the provider account is configured.

## PR74 one-time 0047 guard — prepared, NOT approved

Read-only production preflight on 20 November 2026 confirmed:
- Production PostgreSQL 18.6, database `dawana_db`, role `dawana_db_user`,
  cluster identifier `7705861322388955175`; SSL connected.
- `dic.0046_aftercamp_assessments` recorded, `dic.0047_studio_publications`
  not recorded, and neither new Studio table exists.
- Fresh archive taken by owner on **20 November 2026, 14:35:40 WAT**:
  `dawana_db-PR74-0047-20261120-143540.dump` (442291 bytes),
  SHA-256 `58C489B4A7A3C699725B676B25B462ABC80B25C835B97F3ECC817219AB0BF4B3`.
  `pg_restore` archive readability was verified; **a disposable restore was NOT performed**.
  This archive has not been uploaded into the repository and contains private production data.
- The database provider's free-plan expiry metadata reads 8 December 2026:
  the owner must review upgrade/continuity before camp.

The new `backend/config/studio_0047_migration.py` now pins the owner-reported
fresh backup digest. It still requires an actual verified disposable restoration
(`DAWANA_0047_DISPOSABLE_RESTORE_VERIFIED=yes`), explicit owner approval, and
matching environment evidence. A readable archive is not proof of recoverability. Do **not** use the old
17 November archive to approve 0047. The wrapper
`backend/media-0047-migration-apply-build.sh` intentionally fails the Render
candidate build after a successful DDL transaction to avoid promoting a
schema-incompatible runtime. Only after migration verification, clear one-time
approval variables and allow the normal build.

Before execution, check the final migration source/operation list, current
database identity, backup digest, available recovery route and release commit.
Never apply 0047 merely by deploying the feature branch, running regular
`manage.py migrate`, or setting a guessed approval flag. No migration is
authorized by the presence of these guard files alone.

## Explicit limitations

- Google Meet participants open Google Meet; only a separate supported
  YouTube stream is embedded within DAWANA.
- A YouTube or Vimeo video with embedding disabled cannot be forced to play.
- Scheduled event dates are displayed, but automatic timed future publishing
  and timed push alerts require separate scheduling infrastructure and are
  **not** promised in this release.
- OneSignal delivery requires the organization's own account, subscription
  consent, verified domain and API credentials; no credentials are generated
  or assumed by this code.
