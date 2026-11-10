# Historical recovery sprint baseline — 9 November 2026

Integration target: existing working tree, branch `deployment/container-packaging`,
HEAD `22930f7121720e6f20846ef2e57d6246a804f8d6`. No branch switch or remote update.
Cached `origin/main` is `aa1c1c3`; local `main` is `074c49b`. Production revision
remains unresolved. This is local source preparation, not release approval.

Pre-existing tracked edits: `backend/dic/portal_account_api.py`,
`backend/dic/recovery.py`, `backend/dic/registration_accounts.py`,
`backend/dic/test_registration_accounts.py`, `backend/native-smoke.sh`.
All were copied before editing into ignored
`output/historical-recovery-sprint/preexisting/`. Exact expanded modified/untracked
paths and SHA-256 checksums are in `initial-status.txt` and
`preexisting-manifest.json` there. Existing untracked paths include `.vite/`,
`dawana-platform/dist-correction-pass-3/`, `deployment/`, three production review
directories and ZIPs, a preview-plan JSON, and four fee/preview scripts.

Historical references: independent `.local-preview/premium-portal` at `986b863`
with uncommitted revised Camper World; nested `final-candidate-fonts-v2` and
`earn-points-images-v1`; main-repository stash; verified memories bundle at
`acceptance-artifacts/dic-memories-abb7868.bundle`. Read-only evidence only;
no stash restoration or reference imports. Candidate demo runtimes are excluded.

Current dic migration head: `0038_registration_guardian_declaration`. Historical
`0034_camper_fulfillment` conflicts with current `0034_approved_2026_fees` lineage
and must not be copied unchanged. Current housing queue and payment hooks take
precedence over an alternative historical housing implementation.

Frontend commands: `npm test`, `npm run lint`, production Vite build with a
synthetic HTTPS API base and a separate output directory. Dependencies already
exist; no installation requested. Backend policy harness:
`python -I -B scripts/test_production_policies.py` configures dummy database,
blocks network/database connections and rejects database-backed test classes.
The existing virtual-environment Python launcher currently fails before startup
with Access denied. No Django management/test/migration command against normal
settings is permitted. Database-backed acceptance remains blocked unless an
authorized disposable target is proven. No live providers, emails, content
publication, accounts, registration, workers or hosting activation.
