# DIC 2026 — controlled production population

This is a **production reference-data operation**, not a migration and not a reset. No
records should be copied from local or demo databases. The owner-approved eight
houses are sourced exclusively from `dic/config/dic_2026_houses.json` (ʿUkkāshah,
Al-Barāʾ, ʿAbdullāh ibn Umm Maktūm, Usayd; Nusaybah, Asmāʾ, Umm Sulaym,
Al-Shifāʾ), with four active houses for each gender, capacity 30 each
(240 planned places), official badge colours and unchanged legacy canonical keys.

## Before touching production

1. Verify **Render production PostgreSQL** database identity and the exact
   **2026 edition** (23 December 2026–1 January 2027). Use an authorised
   production operator. Inspect existing houses, housing allocations, housing
   jobs, active edition strategy, guardian relationships and timetables; stop
   on conflicts. Confirm production backup/recovery readiness before writes.
2. Check the current seed file `dic/data/dic2026_approved_release.json`.
   It has **182** timetable rows, including **27** food entries. It reflects
   the 28 December brothers' sports / sisters' workshop and sisters' symposium,
   and 31 December Evening of Gratitude / Final Night adjustments. The
   brothers' after-Asr activity remains TBD, never fabricate it.
3. Run a **read-only preview** on the approved production service:
   `python manage.py initialize_dic2026_release --edition <production-edition-id>`
   Read the printed seed SHA-256. Do not substitute a historical seed hash.
4. Separately approve the exact production database name, edition, actor,
   source SHA-256 and reviewed source content. This document is **not**
   authorization to run the write.

## Population after explicit target approval

Run once from the **Render production Django service**, using its existing
configured production database, not the laptop's local database:

```text
python manage.py initialize_dic2026_release \
  --edition <approved-production-edition-id> \
  --database-name <exact-current-production-database-name> \
  --approved-by <authorized-staff-username> \
  --source-sha256 <reviewed-preview-digest> --apply
```

This command runs atomically. It:

- Creates missing approved houses and safely completes existing matching
  houses with **unset capacity / blank badge colour**, only if no occupants
  exist in the incomplete house; it refuses ambiguous identities, altered
  gender/status/purpose/capacity/colour, and conflicting eligibility rules.
- Preserves existing house PKs, allocations, staff notes, registration,
  payment, check-in and ID records. Existing occupied/inconsistent houses
  require supervisor reconciliation.
- Sets the DIC 2026 housing reference date to 23 December **only if unset**.
  An inconsistent value is a blocker, not silently replaced.
- Creates missing Ta'lim, Tahdheeb and Da'wah classes and certificate
  configuration, and adds approved programme/food **drafts** only. Existing
  timetable edits, manual days, receipt-protected deletions and published
  entries remain untouched.
- Is rerunnable without replacing staff customizations. Audits changes.
- **Does not** approve or activate the housing allocation strategy, start a
  background worker, assign a camper, publish timetables or release certificates.

## Separate housing activation gate

After population, run `check_dic2026_release --edition <id>`, inspect the
eight-house inventory and the `housing_age_reference_date`, then validate
housing-policy invariants against real paid registrations and existing
allocations. The final housing policy requires exactly 4 male + 4 female
**active** participant houses with capacity 30 and no reserves, verified
settlement, appropriate guardian grouping, correct sex/age-band and no
overcapacity. The canonical configuration fingerprint must be explicitly
approved by a housing supervisor; changing houses/date invalidates an old
fingerprint. Do **not** fabricate this approval as part of population.

The existing durable housing queue receives eligible verified-paid registrations
from settlement. **No dedicated Render worker or Docker service is required for
this release.** The existing Render Django backend now offers an authenticated,
CSRF-protected **POST** at `/api/v1/dic/participant/housing/refresh/`.
The Camper Portal loads normally and sends this optional request separately;
the request may claim and process **one pending job belonging to that camper's
verified-paid booking**. It does not process unrelated campers. A missing
housing job can be restored from independently verified paid evidence.

Housing enablement still requires the existing positive
`DIC_AUTOMATION_ACTOR_ID` setting on Render's Django service, identifying
an active staff automation actor with both housing processing and allocation
permissions; and a separately approved housing configuration fingerprint.
This is an application setting, **not** a new Render service.

For any failed/held assignment, the Camper Portal shows only
**"Awaiting house allocation"**. No internal staff reason is shown. The
Operations Portal House Allocation page lists held/failed cases and lets
authorized housing supervisors retry with a recorded reason. The Operations retry attempts the pending allocation immediately on the
existing Render Django service; a later authenticated camper refresh can
also process a pending retry. There are no automatic retries of
supervisor-held work. Payment verification, verified settlement, Camper
Portal login, Digital IDs and existing check-in are not dependent on the
housing result. Housing enqueue failures are isolated in their own database
savepoint; they do not reverse verified payment.

**Limitations:** No constantly running worker means a camper's allocation is
attempted when the authenticated Camper Portal sends its housing refresh
request (or when authorized staff process outstanding jobs). It is not a
guaranteed immediate push immediately following a Paystack webhook. This
deliberately trades background latency for zero additional hosting cost.


## Timetable publication is also separate

The new entries are drafts until an authorised publisher reviews each day
in Django Admin and publishes with existing day-level tools. Confirm gender
and audience filtering (especially 28 December) and today's activities/food
on the Camper Portal. Preserve any later Admin edits; never re-seed over them.

## Release status

Creating this code or passing CI **does not populate Render PostgreSQL**.
The actual count, prior existing data and worker readiness must be checked
on production before reporting the milestone as complete.
