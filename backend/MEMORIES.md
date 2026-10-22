# DIC camp photographs — Stages 1–2

This content system does not use participant records or change registration,
payment, housing or portal behavior. Videos, lecturer profiles and activity
programme management are excluded. Memory activity tags only categorize photos.

## Storage and deployment prerequisites

Install the updated backend requirements (Pillow and boto3). Migration
`0018_memoryactivity_campphotograph` adds two content tables and a tag relation;
it does not populate content or modify registration data. Apply only after
separate staging approval and a database backup. It depends on migration 0017.

Development uses private local storage under `backend/media/private-memories`.
Never expose this directory through MEDIA_URL, a static web server, or a CDN.
Non-development uploads default to disabled; the local backend refuses to run
with DEBUG=False. Do not use Render's filesystem for uploads.

Before enabling uploads on Render, provision and verify a PRIVATE S3-compatible
bucket with public access blocked and no public bucket policy. Configure:

- `DIC_MEMORY_STORAGE=s3`
- `DIC_MEMORY_S3_BUCKET`: private bucket name
- `DIC_MEMORY_S3_ENDPOINT`: provider HTTPS endpoint, or empty for AWS S3
- `DIC_MEMORY_S3_REGION`: provider region
- Credentials through the standard boto3 credential chain, such as securely
  configured `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. Never put them in
  source control or browser settings.

Use a service identity restricted to GetObject and PutObject within the
`memories/` prefix. Verify that anonymous direct object requests fail. The public
API streams only published photographs after checking publication state; it
never returns storage keys, object URLs or credentials. No presigned URLs are
issued. Responses are private/no-store. Withdrawal blocks subsequent requests,
but cannot retract images already downloaded by a viewer.

Uploads accept still JPEG/PNG/WebP images up to 12 MB and 20 megapixels. Files
are re-encoded to JPEG, resized to a maximum 2400-pixel edge, stripped of image
metadata and stored with generated names. Original filenames are not retained.
Review consent and photograph content before publication; sanitizing metadata
does not remove identifying information visible within a photograph.

## Django Admin workflow

1. Assign media staff add/change/view Camp photograph permissions and the
   appropriate Memory activity tag permissions. Do NOT grant publication rights.
2. Assign designated publishers view/change Camp photograph plus the separate
   **Can approve and publish camp photographs** permission. Active superusers
   have these permissions. No role or account is provisioned automatically.
3. Create activity tags only when supplied by the committee. Add a photograph,
   choose its existing camp edition and tags, and enter caption and useful alt
   text. Set featured/display order, then save Draft or Ready for review.
4. Use the authenticated Private preview link to inspect the image. Check that
   the photograph and caption are approved for public use.
5. A publisher selects photos in the list and runs **Approve and publish selected
   photographs**. Actor and timestamp are recorded, with an admin audit event.
6. Use **Withdraw selected photographs** to remove them from public access.
   Editing published content returns it to review. Renaming a tag also withdraws
   its published photographs pending approval. Tag deletion is disabled.

No sample camp photos, participant links or invented editions are created.
Featured photographs appear first, then display order and primary key. The
initial public response is capped at 200 photos; filters apply to that loaded
collection. Additional pagination can be introduced if the archive grows.

## Verification and rollback

Backend: `dic.test_memories`, registration/payment regression suites; all storage
provider calls in tests are mocked. Use only a separate local test database.
Frontend: npm test, lint, build; then run `scripts/check-memories-ui.cjs` and
`scripts/check-registration-ui.cjs` against local Vite on port 5178. Both browser
scripts intercept APIs and external traffic with synthetic fixtures.

Before staging: approve dependencies/migration, verify private storage and
authorization using non-sensitive test content, and validate the existing API
proxy can stream JPEG responses without public caching. No storage credentials
or environment values have been configured by this implementation.

Rollback the frontend/backend artifacts together, retaining content tables and
private objects. Disable new uploads if necessary; do not delete photos or
reverse migrations as an automatic rollback. Back up database and objects under
the agreed retention policy. Replaced/deleted records can leave private orphan
objects; cleanup requires a separate retention decision.
