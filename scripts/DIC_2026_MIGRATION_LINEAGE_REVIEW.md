# DIC 2026 — read-only migration-lineage review

26 October 2026. **Review only. No migration, schema, data, configuration or permission changed.** DOB, height and weight remain mandatory. Paystack and assisted booking were not activated. No record-creating tests ran.

## Current graph and evidence

Static inspection of migration dependency lists found the dic chain `0001 → … → 0025_camp_check_in → 0026_house_score_transaction → 0027_feedback_welfare`. No checked-in migration directly or transitively depends on 0027. Supporting nodes `dic_finance.0001_initial`, `dic_movement.0001_initial`, `dic_assistance.0001_initial` and `dic_scoring.0001_activity_award` depend on 0026, not 0027. Auth dependencies use the swappable accounts model. No migration `run_before`, replacement or settings `MIGRATION_MODULES` override was found. This is source inspection, not execution of Django MigrationLoader; Python still returns Access is denied.

**Direct database verification succeeded using installed PostgreSQL 17 psql**, without Python. Connections used existing local credentials privately, `--no-psqlrc`, no password prompt, a short connection/statement timeout and `default_transaction_read_only=on`. Queries selected migration metadata/schema metadata only. Environment variables were restored afterward; no credentials are included here.

`dawana_dev` identity: **127.0.0.1:5432**, read-only setting `on`. Recorded dic migrations are 0001–0026; 0027 is absent. Assistance, Finance and Movement initial migrations and Scoring initial migration are recorded applied. All six proposed feedback/welfare tables are absent. `dic_participant.date_of_birth`, `height_cm`, `weight_kg` each have `is_nullable=NO`. This independently confirms the latest user-supplied development status.

## Environments checked and limits

Read-only history queries succeeded for **34 local non-template application/test/demo databases** on that server; the `postgres` maintenance database was only part of the name inventory, not an application-history check. Results concern recorded migration names, not full schema equivalence for every test DB.

| Local database group | 0026 | 0027 | Assistance initial |
| --- | --- | --- | --- |
| `dawana_dev` | Applied | Absent | Applied |
| `test_dic_assistance_20261026181707_292d724d` | Applied | Absent | Applied |
| `test_dic_portal_2026_local` (protected OTP) | Applied | Absent | Absent |
| `test_dic_finance_20261025223457_c8e898d0`, `test_dic_finance_20261025224147_d6f836fe`, `test_dic_movement_20261026160308_028b42e8` | Applied | Absent | Absent |
| `test_dawana_validation_20261025092235_1c89490db8` | Applied | Absent | Absent |
| Six validation databases listed below | Applied | **Applied** | Absent |
| Remaining 21 local older validation/demo/test databases | Absent | Absent | Absent |

**0027 is already applied in these six databases:**

```text
test_dawana_validation_20261025102430_c93eef1c5a
test_dawana_validation_20261025104339_f461d45a0a
test_dawana_validation_20261025114348_3eb9bd060d
test_dawana_validation_20261025120932_08f32c6bfc
test_dawana_validation_20261025121815_69d4532cd1
test_dawana_validation_20261025122949_656057b5a4
```

They were only read, not reset or classified as safe to destroy merely from their names. The follow-up provenance review below confirms test-only creation and explicit evidence retention, not deletion approval. A blanket assertion that 0027 has never been applied is **false locally**.

## Follow-up: database provenance and non-destructive disposition

The following exact-name matches were found in existing `validation-results/*.json` and corresponding `.txt` logs. Every summary records `database_created=true` and `database_cleanup="none: newly created validation database is deliberately retained"`. All twelve report/log files still exist. Historical results below are evidence read from those reports, **not tests rerun in this review**.

| Exact database | Matching report/log stem under validation-results | Historical result | Disposition |
| --- | --- | --- | --- |
| `test_dawana_validation_20261025102430_c93eef1c5a` | `20261025T102429Z-d8a049` | FAIL: 21 executed, 0 failures, 1 error; feedback | Retain failure diagnosis evidence |
| `test_dawana_validation_20261025104339_f461d45a0a` | `20261025T104337Z-3f524f` | PASS: 24/24, feedback | Retain passing baseline |
| `test_dawana_validation_20261025114348_3eb9bd060d` | `20261025T114347Z-3f5e4b` | PASS: 26/26, feedback/postponement | Retain passing baseline |
| `test_dawana_validation_20261025120932_08f32c6bfc` | `20261025T120928Z-b0412b` | FAIL: 129 executed, 1 failure, 0 errors; ID/portal/registration/privacy | Retain failure evidence and print fixtures |
| `test_dawana_validation_20261025121815_69d4532cd1` | `20261025T121813Z-4973dc` | PASS: 130/130, ID/portal/registration/privacy | Retain passing evidence and print fixtures |
| `test_dawana_validation_20261025122949_656057b5a4` | `20261025T122948Z-e53a68` | PASS: 130/130, ID/portal/registration/privacy | Retain passing evidence and print fixtures |

**Origin assessment for each: confirmed fresh isolated validation creation, intended to be disposable test infrastructure, but deliberately retained evidence.** This follows exact report-name linkage plus `scripts/validate_dic_backend.py`, not the database prefix alone. That runner generates timestamp/UUID names internally, refuses pre-existing names, creates a fresh database, substitutes synthetic keys/local test settings, selects test fixtures and uses DiscoverRunner `keepdb=True`. `scripts/BACKEND_VALIDATION.md` explicitly says retention is for inspection and cleanup requires separate authorization naming the database. The first three reports contain feedback tests; the final three contain the broader module mix listed above. Current `dic/test_feedback.py` uses a SYNTHETIC edition/staff and isolated TestCase fixtures. Current source corroborates purpose but is not independent proof of every historical source byte.

Print artifact directories for the last three runs are recorded in their JSON and **still exist** at `.local-preview/id-print-qa/<exact database name>/`. Keep them with the matching summaries/logs. Test teardown may remove fixture rows while leaving schema/history and files; a retained database is not necessarily a complete snapshot of every failed test's transient state.

**Protection versus retention:** none of these six names is listed in the inspected explicit `PROTECTED` set. `scripts/validate_dic_finance.py` explicitly protects `dawana_dev` and `test_dic_portal_2026_local`; the OTP helper/documentation preserves its distinct unpaid fixture and recovery setup. `test_dawana_dev` is also deliberately inspected read-only and not reused by the legacy validation runner. Those databases are separate from the six. Lack of an explicit protected-name flag does **not** override the six reports' retention instruction or authorize deletion. No evidence of required real camper/payment records in the six was found in the reviewed creation reports/fixtures; their current business-row contents and later manual use were **not inspected**, so no guarantee of exclusively synthetic present-day contents or safe disposal is made.

### Configurations and deployment risk

Staging configuration exists in `backend/config/settings/staging.py` and `backend/staging.env.example`: it requires an explicit PostgreSQL DATABASE_URL and matching STAGING_DATABASE_NAME, inherits production security and requires TLS. Production configuration exists in `backend/config/settings/production.py`, inheriting the base PostgreSQL configuration, which accepts DATABASE_URL or DB_* values. Example keys and settings were inspected; no remote credential values were printed, changed or used. Their existence proves configuration support, not a deployed service or known migration history.

`backend/render-migrate.sh` currently executes **unrestricted `python manage.py migrate --noinput`**, followed by cache-table creation and migration check. It would include deferred 0027 even after a run_before insertion. This is a release blocker for using that script in a Phase 2-only deployment. Any future targeted deployment-script correction requires approval and verification; none is made here. `backend/render-start.sh` starts the staging application and does not itself migrate. Remote staging/production remain unverified and were not contacted in this follow-up.

### Separate safety assessments

- **dawana_dev:** the previously verified 0026-applied/0027-absent history is a compatible starting point for a new Phase 2 predecessor of 0027. No records need to be discarded and original 0027 can remain unchanged. This is **graph-level compatibility only**, conditional on rechecking history at implementation time and validating the actual future migration, nullability policy, deployment target and dependent consumers. It is not current approval to create/apply that migration.
- **The six older validation DBs:** loading a future graph that inserts a missing prerequisite before their already-applied 0027 makes their histories inconsistent for Django migration operations. Even attempting to target the new node can be refused by history checks. Their current graphs remain coherent with their original migration code. They need not be deleted, reset, faked or rolled back. Keep them as **legacy evidence databases outside the receiving Phase 2 deployment set**, associated with the original migration graph. Do not point new application servers, validators, migration commands or shared test discovery at them. Merely retaining them on the same PostgreSQL server does not make a migration connection to dawana_dev inconsistent; history checks operate per selected connection.

### Precise non-destructive recommendation

1. Preserve all six databases unchanged and document them as legacy validation evidence, not future test targets. This is the default recommendation, replacing any implication that deletion is necessary to proceed. Preserve `dawana_dev`, OTP and other protected databases independently.
2. Preserve the twelve report/log files and three print artifact directories listed above. Before future graph changes, obtain approval to archive a checksum manifest, the exact historical migration files and supporting validation source, available source revision identifiers and known fixture dependencies. Do not infer an exact historical Git commit from a run timestamp. An isolated historical checkout/artifact bundle can provide the old graph for future investigation; its services must not connect automatically. No archive or checkout was created during this review.
3. If database portability/long-term recovery is needed, separately approve read-only custom-format pg_dump backups of these exact six names plus a manifest of database identity and migration history, then verify archive readability/checksums without restoring over any existing database. Restrict access because later manual use is unverified. No dump, grant, restore or backup write was performed here. Existing originals remain the primary retained evidence until backups are verified.
4. Scope the new migration graph to verified receiving environments with 0027 absent. Obtain staging/production owner evidence; if an operational receiving DB has 0027 applied, **stop and redesign compatibility** rather than silently excluding that operational DB. Keep old evidence databases outside that release scope by explicit owner decision. Do not rename/delete 0027 or fake the six histories.
5. After approval, prepare the already proposed `0026 → 0028_registration_privacy_measurements → 0027` ordering and use fresh, separately approved disposable databases for Phase 2 validation. Never reuse the six legacy DBs. Prove graph/model consistency and target-plan exclusion, then obtain separate application approval. Fix the unrestricted staging migration path through its own reviewed change before deployment. Phase 5 continues to require separate authorization.

**Explicit approval checklist (nothing below is auto-approved by this review):**

- [ ] Owner accepts the six exact names as retained legacy evidence, excluded from new application/test/migration targets; no deletion/reset is required.
- [ ] Owner confirms whether any later manual data or legal/operational retention obligation exists in those DBs; until then retain originals and treat exports as potentially sensitive.
- [ ] Approve evidence archival/checksum/source capture; separately approve database backups if wanted. Verify archives before considering any later cleanup request.
- [ ] Obtain fresh read-only migration/table evidence from every receiving staging/production/other retained operational environment; no unverified environment receives the reordered graph.
- [ ] Approve the new run_before insertion specifically for 0027-absent receiving DBs, with old evidence DBs pinned to their original graph. If any retained receiving operational DB has 0027 applied, require a new compatibility design.
- [ ] Approve a focused correction of deployment/test migration targeting, including `render-migrate.sh`; no unrestricted migration while Phase 5 is deferred.
- [ ] Approve coherent adult/minor/nullability policy, implementation and fresh disposable validation. Migration preparation and later application remain distinct approvals.

Follow-up execution: repository/report/fixture inspection only; no new database connections, remote connections, test runs, backups, migration/code edits, model changes or activation. Only this review document was updated. **Stop pending approval.**

**Not verified:** remote staging, production, colleagues' machines, CI databases, backup/restored databases or any PostgreSQL server beyond this loopback instance. Staging/production settings exist (`backend/config/settings/staging.py`, `production.py`), but settings/source presence does not prove a deployment or its history. No remote database access was attempted or credentials requested. Their owners must supply read-only history and table-presence evidence before graph changes are approved.

## What 0027 does

`backend/dic/migrations/0027_feedback_welfare.py` contains six CreateModel operations: AnonymousCamperResponse, CamperFeedbackReceipt, LecturerFeedbackAccess, IdentifiedFeedback, WelfareReport and WelfareEvent. It creates their tables, keys, constraints and model permission state. It references existing edition, lecturer, primary registrant, user and welfare-report identities. It has **no RunPython, RunSQL, participant alteration, backfill or payment operation**. Thus its operations are largely independent of participant nullability, but a changed graph still affects history consistency.

The six runtime model classes remain registered under dic via `models.py`/`feedback_models.py`; feedback storage checks expect these tables. Moving them to another app would also change historical ownership, content types/permission labels, imports and possibly table names. A supporting app alone cannot change the core Participant field constraints. Existing scripts explicitly reference 0027; any future rename/relocation needs a complete reference/guard review, not only a filename change.

## Options and risks

| Approach | Assessment |
| --- | --- |
| Preserve 0027 and put Phase 2 after it | Most compatible with existing applied histories, but requires Phase 5 schema before Phase 2. Does not meet the requested separation; reject for this objective. |
| Rename/renumber/reparent the postponed migration | Feasible only under coordinated approval and proven never-applied status in every retained receiving DB. Already-applied names would be orphaned or new names would try to recreate tables; changing dependencies can make history inconsistent. The six local applied histories and unverified remote histories block this now. Moving models to a supporting app adds more ownership risk. |
| Parallel Phase 2 branch from 0026 and merge | A future merge depends on both heads, so applying it includes Phase 5. Leaving two heads requires special operational tooling and causes normal migration conflict checks; targeted migration is not a complete cure. Adds deployment risk without durable separation. Reject. |
| **New Phase 2 migration with documented `run_before` ordering** | Keeps the original 0027 file/name/operations untouched. A new core node depends on 0026 and orders itself before 0027, producing one linear graph. Django supports this when editing the successor's dependencies is impractical. **It still changes effective history:** any DB with 0027 already applied but the new prerequisite absent becomes inconsistent. Requires explicit disposition of the six local applied histories and evidence from every retained receiving environment. Conditional preferred approach. |
| Routers, fake application, replacement/squash or mismatched SQL/state | Not a safe phase-separation shortcut. They risk recorded migrations without intended tables, missing historical state or duplicate ownership. No such workaround recommended. |

Django orders by graph edges, not filename numbers. The official documentation supports `run_before`, prefers direct dependencies where practical, and warns that missing dependencies of applied migrations cause refusal. See [migration ordering](https://docs.djangoproject.com/en/5.2/howto/writing-migrations/#controlling-the-order-of-migrations) and [history consistency](https://docs.djangoproject.com/en/5.2/topics/migrations/#history-consistency).

## Recommendation and exact proposed sequence

**Conditionally prefer preserving 0027 unchanged and adding a core Phase 2 migration ordered before it with `run_before`. Do not implement this yet.** This reduces migration-file/ownership churn compared with relocation and avoids an unresolved branch. It is not approved for databases with 0027 already applied. The follow-up recommendation above preserves those six as legacy evidence outside the receiving deployment lineage. If any such database must receive the new graph, stop: this recommendation cannot be rolled out unchanged, and a separately designed compatibility transition is needed. No fake/rollback remedy is authorized.

Proposed names/edges, **not created**:

```text
dic.0026_house_score_transaction
  → dic.0028_registration_privacy_measurements   [Phase 2]
  → dic.0027_feedback_welfare                    [Phase 5; unchanged file]
```

The proposed Phase 2 class would declare `dependencies=[('dic','0026_house_score_transaction')]` and `run_before=[('dic','0027_feedback_welfare')]`. Required extra auth/supporting dependencies must be reviewed if its eventual operations use them. Despite its smaller number, 0027 becomes the graph successor. This is graph linearization, not an unresolved sibling branch or a merge.

1. Inventory every retained receiving environment and freeze concurrent migration changes. Obtain owner-approved disposition for the six local 0027-applied validation DBs. Preserve any needed evidence. No disposal/recreation is performed in this review.
2. Approve the graph design and coherent privacy schema/policy. Prepare only the new core migration and null-safe frontend/backend changes; retain all historical files. Preserve historical values and snapshots; never synthesize DOB/measurements. Adult/minor safeguards and category/housing evidence handling remain mandatory.
3. In a fresh approved disposable DB, prove MigrationLoader conflict-free history, model parity, fresh install, upgrade from 0026 plus existing supporting migrations and **Phase 2 target plan excluding 0027**. Keep application flags off. Test adult/minor/measurement combinations and dependent consumers. Also inspect the future Phase 5 plan for exactly its intended work.
4. After separate explicit approval, target **`migrate dic 0028_registration_privacy_measurements`**, never broad `migrate`, on each verified deployment. Expected incremental dic schema work from current development state: Phase 2 only. This is a proposed command, not permission to execute it now.
5. Only during Phase 5, after its own security/privacy approval, target **`migrate dic 0027_feedback_welfare`**. Its forward plan will include Phase 2 if missing. Any additional Phase 2 nodes must also be explicitly ordered before 0027; do not let future automatic migrations silently depend on the deferred leaf.

An unrestricted migrate or standard test-database setup still targets the latest leaf (0027) and would apply Phase 5. Explicit deployment/test target guards must remain. Downgrading back to code without the new node can also leave an unknown applied history; coordinate code rollback and prefer disabling functionality over reversing nullable data. Nullable DOB cannot safely be made non-null once withheld records exist without real evidence.

## Approval gates and stop point

Required before changes: environment-history sign-off; approved disposition of 0027-applied disposable histories (or a revised compatibility plan); approval of `run_before` graph insertion and future target discipline; adult assertion/evidence and age-dependent review policy; reviewed nullability/snapshot compatibility; isolated test plan. Schema application and any test-database retirement require separate explicit approval after implementation evidence.

This review creates only this document. Earlier authorized frontend changes and their focused results are listed in `DIC_2026_UI_AND_REGISTRATION_PRIVACY_REVIEW.md`: 16 checks, lint and build passed. No migrations were generated/edited/applied; no records were created. **Stop here pending approval.**
