# DIC Stage 4 — lecturers and approved activities

Based on Stage 3 `b285bc61656876b138b479ac488a824c7c90b5b8` in an independent
local clone. No dirty-tree merge, cherry-pick, production change or payment change.

## Content model and approval

Lecturer stores identity, private photograph/alt text, short biography and
designation. Reuse that identity for multiple edition-linked LecturerAppearance
records; a unique constraint prevents duplicate appearances for the same identity
and edition. Staff must search existing identities before adding a new one:
names alone are not treated as unique personal identifiers.

An appearance records previous/upcoming participation, topic, invitation status,
private verification note, verifier/time, featured/order and moderation metadata.
CampActivity stores edition, title, description, free-text committee-approved
category, optional private image/alt text and its own moderation metadata.
No names, topics, activities, schedules or photographs are seeded.

The API returns only published content. Upcoming lecturers and activities are
limited to edition year 2026. Previous lecturer appearances have an edition filter.
Explicit administrative previous/upcoming designation is used rather than the
browser clock. Historical topics are suppressed unless participation/topic
verification is recorded. Upcoming profiles may be published while pending, but
are labelled awaiting confirmation. A database status flag alone is insufficient
for a confirmed label: verifier, timestamp and nonblank evidence are required.
Declined appearances cannot be published.

## Django Admin

1. Give media editors add/change/view Lecturer, Lecturer appearance and Camp
   activity permissions, without publication or verification permissions.
2. Give designated publishers change/view plus `publish_lecturerappearance` and/or
   `publish_campactivity`. Photo/video publication permissions do not grant these.
3. Give authorized invitation/topic verifiers change/view Lecturer appearance and
   the separate `verify_lecturerappearance` permission. Superusers must be active.
4. Add or reuse a Lecturer. Only approved identity content should be entered.
   Private preview requires staff status and the model's view permission.
5. Add an appearance with its edition and previous/upcoming type. Record an
   invitation state, approved topic and private evidence as appropriate. Save
   Draft or Ready for review. Ordinary forms cannot set Published or Confirmed.
6. A verifier selects an appearance and uses Verify participation and lecture
   topic using recorded evidence. This requires a nonblank verification note,
   records actor/time, and leaves the appearance in review, NOT published.
7. A publisher uses Approve and publish selected content. Pending upcoming
   appearances can be approved but never presented as confirmed.
8. Create activities only from approved committee material, select the edition,
   enter category/description, and optionally upload a photo with meaningful alt
   text. A publisher approves it separately. Images are not required for an activity.
9. Withdraw selected content to remove public access. Published edits go back to
   review. Editing an appearance through the form resets confirmed participation,
   requiring verification again. Identity edits withdraw every published linked
   appearance and reset its verification; these effects span editions deliberately.

Editorial creation/edit, publication/withdrawal, identity changes and participation
verification produce administrative audit events. Identity changes and appearance
publication lock the Lecturer before appearance rows to avoid approval races.

## Private images

Uses existing PrivateMemoryStorage and image normalization; no new dependencies
or media credentials. Draft identity images have no public endpoint. Published
lecturer image URLs address the approved appearance, not an unrestricted identity
record. Activity images similarly require publication. Preview endpoints require
staff plus model view permission; all images use private/no-store headers.
Do not mount the private media directory publicly. Previously downloaded images
cannot be retracted; the service blocks new requests after withdrawal.

Render uploads remain disabled until S3-compatible private storage is configured
and verified. See MEMORIES.md for environment names, credential handling, bucket
privacy and role setup. No configuration values were changed here.

## Migration and deployment prerequisites

`0020_lecturer_campactivity_lecturerappearance` adds three tables, permissions and
the lecturer/edition uniqueness constraint. It depends on 0019. Existing 0018 and
0019 files are unchanged. No participant links, seeds or data rewrites exist.

Before staging: review/approve the diff, back up PostgreSQL and private objects,
approve the additive migrations, install existing photo dependencies, assign
editor/publisher/verifier permissions, and verify storage and images through the
same-origin API proxy. Validate only consented committee-approved content.
Rollback application artifacts together while retaining additive tables, objects
and audit history; do not automatically reverse migrations or delete content.

## Checks

Use separate local PostgreSQL test DB only. Run dic.test_showcase alongside photo,
video, registration, payment and payment-return regressions. Frontend npm test,
lint, build. With local Vite on 5178 run check-showcase-ui.cjs, check-memories-ui.cjs,
check-videos-ui.cjs and check-registration-ui.cjs. Fixtures are synthetic and external
traffic is intercepted. Public collections are bounded (100 upcoming, 200 previous,
200 activities); archive pagination is not implemented in this stage.
