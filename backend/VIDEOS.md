# DIC Memories — Stage 3 video gallery

This implementation is based on the isolated Stages 1–2 commit
`abb7868c095c28a351e6944b54db0ed170c246f1`. It reuses CampEdition,
MemoryActivity photo tags, private image storage, moderation states and the
existing admin audit table. Registration, payment, housing and portal code is
unchanged. The dirty original workspace was not merged or cherry-picked.

## Provider approval

YouTube and Vimeo were explicitly approved for Stage 3. Local development
enables these two supported providers. Deployment settings default to accepting
none until the operator configures `DIC_VIDEO_APPROVED_PROVIDERS` as a
comma-separated list of the approved identifiers `youtube,vimeo`. No environment
values were changed by this implementation. Unknown identifiers enable nothing.

Only supported HTTPS URLs with exact recognized hostnames and valid video IDs
are accepted. Credentials, custom ports, fragments, direct media-file links,
arbitrary embed HTML and unsupported hosts are rejected. Accepted IDs produce
canonical youtube-nocookie.com or player.vimeo.com iframe URLs. User URL query
parameters are never forwarded to the player. Duplicate YouTube `v` parameters
are rejected. The backend never fetches video URLs or remote thumbnails.

The public list contains no original hosted URLs or embed URLs. After a visitor
selects a recording, a separate GET rechecks publication and provider approval.
Revoking a provider hides its entries and prevents new playback/thumbnail
requests, including when the database record still says published. Withdrawal
and tag-change review actions remain available for revoked-provider records.
Already loaded third-party playback cannot be retracted by server-side changes.

The app protects its own draft APIs and thumbnails; it cannot make an externally
hosted public video private. Do not paste secret-bearing/private provider links.
Only public or appropriately approved unlisted recordings with embedding
permitted are supported. Provider privacy, rights, captions and embedding rules
must be reviewed before publication.

## Admin workflow

1. Assign media staff add/change/view Camp video permissions plus appropriate
   Memory activity tag permissions. Photo publication permission does not grant
   video publication permission.
2. Assign designated publishers view/change Camp video and the separate
   `publish_campvideo` permission. Active superusers can publish.
3. Create a Camp video: select its existing edition and approved activity tags,
   enter the hosted URL, caption, meaningful thumbnail alt text, featured status
   and order, and upload an approved still thumbnail. Save Draft or Ready for
   review. No video-file upload or transcoding exists.
4. Review the source recording on its provider and use the authenticated private
   thumbnail preview. Confirm consent, accuracy, playback, captions and rights.
5. Use Approve and publish selected videos. Actor/time and an audit event are
   recorded. Public lists use featured first, then display order and primary key.
6. Withdraw selected videos removes public access. Editing the record or its
   activity tag returns it to review; publication requires renewed approval.

Thumbnails use the Stage 1 private storage architecture and file validation,
metadata stripping and re-encoding. Render uploads remain dependent on verified
private S3-compatible storage. Never expose its local upload directory.

## Migration and staging prerequisites

`0019_campvideo` depends on 0018 and adds the CampVideo table, activity relation,
and permissions. No data seed, video content or existing-record rewrite occurs.
No new dependencies are required beyond the photo implementation.

Before an approved staging deployment: review the uncommitted diff, preserve
the isolated photo commit, verify storage, install the photo dependencies,
back up PostgreSQL, approve/apply pending 0018 and 0019 migrations, assign roles,
and configure the approved provider list. Do not run tests against staging.

If a Content Security Policy is configured at the hosting layer, its frame-src
must allow only the approved canonical player origins. No preconnects, iframes,
player SDKs or provider thumbnail requests occur before selection. Providers
receive a request only when the visitor opens a recording. Native provider
controls remain enabled; autoplay permission is omitted. Requests send an origin
referrer, which provider players may require for embedding authorization.

## Validation and rollback

Backend tests cover provider validation/spoofing, drafts, publication rights,
filtering/order, private thumbnails, revocation, audit history and tag edits.
Run the photo, registration, payment and payment-return regressions as well.
Frontend: npm test, lint, build. Browser scripts `check-videos-ui.cjs`,
`check-memories-ui.cjs` and `check-registration-ui.cjs` run against local Vite
on port 5178 and intercept external/API requests with synthetic responses.
No actual third-party playback, registrations or payments are initiated by tests.

Real provider playback, caption availability, hosting CSP and private object
storage still require an approved staging acceptance check. The galleries load
at most 200 published entries each; pagination is outside this stage.

Rollback backend/frontend artifacts together, retaining the additive database
tables, thumbnail objects and audit history. Disable provider approval or
withdraw videos when needed. Do not reverse migrations or delete content as
an automatic rollback. No commit, push, deployment or remote migration is part
of this implementation step.
