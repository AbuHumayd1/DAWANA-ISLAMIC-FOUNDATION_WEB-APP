# DIC 2026 — Phase 2 Increment 1: safe assisted-registration foundation

26 October 2026. **Safe independent components implemented; staff-created booking/payment handoff is not enabled.** This follows the request's explicit fallback where secure assisted creation requires new schema. No new model/migration, database write, payment, account, permission grant or core constraint change was performed. No Phase 3, invitations, age-band schema or academic allocation work was started.

## Architecture followed and exact blocker

Read `DIC_2026_PHASE2_ARCHITECTURE_PLAN.md`, especially section 3.3. The existing `views._create_order()` already validates categories, age, registration windows, pricing, snapshots and public request idempotency. It creates internal enrollments before payment; trusted payment verification remains required for paid eligibility and active ID issuance. Existing recovery/restore gives the payer ownership on their own browser; existing PaymentReturnGrant is browser-session-bound.

A secure **staff-created** registration requires the durable `RegistrationAssistance` association proposed by that plan: assisting actor, order, edition, unique request/fingerprint, ownership for retries and minimal status access. The public retry branch rotates the order's access token. Calling it blindly again after the payer recovers the booking could invalidate payer ownership. Anonymous new requests can also create new person UUIDs; name/contact similarity is not reliable identity proof.

The existing generic audit-event table has no unique assistance-request/ownership relationship. It can log creation but is not a safe substitute for an enforceable assistance association. This increment does **not** use audit JSON queries as an authorization or uniqueness workaround, expose payer tokens to the officer, turn a browser session into payer authority, or add a generic model-add permission to all staff.

**Precise blocker:** approval/design of a narrowly scoped additive assistance table, its explicit mutation permission and known-person/order reuse checks. No second payment processor or authentication system is needed. A supporting-app migration can likely reference dic 0026 without depending on postponed dic 0027, but that new schema is not generated or applied under this increment's fallback scope.

## Functionality implemented

### Existing Operations route and navigation

New route: `/dic/operations/assisted-registration`, labelled **Registration preparation** under Participants & Registration. The existing Operations login/session shell is reused. It requires the active-staff campsite capability. There is no new staff-created-booking privilege; the visible page is explicitly preparation/guidance only.

The page explains payer-owned-device registration, existing-booking recovery instead of another registration, backend-only payment evidence and the prohibition on sharing officer cookies, browser storage, payer OTPs/tokens or payment credentials. It reads existing public registration options and recovery-channel metadata; it does not send OTPs or invoke Paystack. Missing/unloaded recovery status is distinguished from channels actually reported unavailable. Reported channel availability is not a guarantee of successful delivery.

Registration must still be open to display the optional preparation form. Staff cannot override registration windows here. A reachable approved website address is required on another phone; a laptop localhost URL is not a cross-device handoff address.

### Stateless field-preparation endpoint

`GET /api/v1/dic/operations/assisted-registration/` returns `mode=preparation_only`, `creation_enabled=false` and the existing public registration/recovery paths.

`POST` to the same endpoint accepts exactly:

```text
{ registration: <existing RegistrationOrderCreateSerializer payload> }
```

It reuses `RegistrationOrderCreateSerializer` and its nested strict participant serializer. Required exact DOB, all current rich camper fields, decimal precision, enumerated options and future-DOB rejection are retained. For useful future recovery, it additionally requires the payer/responsible registrant name and own email/phone; a supplied recovery phone must normalize through existing recovery validation. It does not verify that an officer entered the rightful contact: real contact verification remains on the payer's existing flow.

Anonymous, inactive, nonstaff and non-Operations access is rejected before validation by existing session/Operations authorization plus active-staff checks. Existing session CSRF and no-store behavior are inherited. No new authentication architecture was added. All active Operations staff can use this non-mutating preparation page; **no role gains order creation or access to another payer's booking**. A dedicated assistance permission must gate future booking creation.

Response explicitly states `fields_valid=true`, `registration_created=false`, `payment_started=false`. It contains no personal payload, booking/access token or participant identifier. This is only a **field check**, not category existence, final age-range eligibility, pricing reservation, identity matching, payment success or admission approval. Those domain checks remain in the existing registration/verification services. Injected payment/status/actor/amount/exemption/token fields fail strict validation.

The optional single-camper mobile-friendly form includes all current mandatory fields, category and payer recovery contact. It submits only field preparation. There is no Register/Pay/Mark paid/Issue QR control. Values are held in the current DOM/request memory only; no saved draft/localStorage/sessionStorage or URL payload is introduced. Clear removes fields, and changing/resetting fields clears the previous success notice. No staff/order association is persisted because no order is created.

### Payer flow that remains usable today

For a new booking, the payer completes the **existing** public `/dic/register` flow on their own device, with staff guidance if needed. For an existing booking, use `/dic/register/recover`, verify its registered contact, restore that same booking, accept current pricing and complete the existing Paystack checkout. These paths and their authentication/payment behavior were inspected and left unchanged.

This does **not** claim that the prep form transfers its private fields or an officer-created booking to another device. There is no new handoff token, cross-browser cookie transfer, automatic payment initialization or officer monitoring ownership path. Actual staff-created intake, enforceable duplicate-order/person selection and actor/order audit association are deferred together behind the schema gate.

## Verification performed

From `dawana-platform`:

```text
node --test src/services/assistedRegistration.test.js src/services/operationsRefinement.test.js
12 passed; 0 failed; 0 skipped.

oxlint src/pages/AssistedRegistration.jsx src/services/assistedRegistration.js src/services/assistedRegistration.test.js src/pages/Operations.jsx src/services/operationsNavigation.js src/services/operationsRefinement.test.js
Passed without warnings.

npm.cmd run build
Passed; existing bundle-size warning (main JS approximately 616 kB minified).
```

Five new frontend tests cover exact payload/decimal/DOB retention, required fields/contact, absence of payment/ownership override fields, repeatable field-preparation payloads, staff-only navigation, required form controls, explicit non-creation messaging and existing payer/recovery links/status. Seven affected navigation/layout checks also passed. One old navigation-count assertion was updated from 16 to 17 for the new page. No full frontend suite was run.

Prepared `dic.test_assisted_preparation.AssistedPreparationTests`: **10 database-free tests** covering compatibility with the existing input serializer, all required camper fields, future DOB, forbidden payment/role/token overrides, recovery contact, staff authorization, disabled-creation metadata, repeated validation without order/payment/eligibility calls and malformed/create-action rejection.

Invoking `scripts/validate_dic_assisted_preparation.py` failed before Python started because the configured Python313 base executable is inaccessible. **These 10 backend tests did not execute.** No database was created or connected to. The guarded runner forbids DB connections and external provider/delivery calls; normal VS Code command:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
& .\backend\.venv\Scripts\python.exe -B .\scripts\validate_dic_assisted_preparation.py
if ($LASTEXITCODE -ne 0) { throw 'Assisted-preparation checks failed or runtime remains inaccessible.' }
```

Existing end-to-end paid registration, recovery delivery/restore, payment verification/fulfillment, duplicate-charge protection and QR eligibility were **inspected, not rerun or newly certified**. Their source files and policies were not modified. No actual Paystack transaction, payment initialization, camper creation/edit or activation test was attempted. Repeated prep cannot create duplicates because this increment has no creation path; that is not proof of the future assisted-creation concurrency workflow.

## Exact files changed

1. `backend/dic/assisted_registration.py` — strict stateless preparation wrapper and existing-session active-staff API; creation explicitly disabled.
2. `backend/dic/urls.py` — preparation-only endpoint.
3. `backend/dic/test_assisted_preparation.py` — ten DB-free input/auth/non-mutation checks.
4. `dawana-platform/src/pages/AssistedRegistration.jsx` — preparation form and payer-owned registration/recovery guidance.
5. `dawana-platform/src/pages/AssistedRegistration.css` — responsive Operations-compatible fields/focus styling.
6. `dawana-platform/src/services/assistedRegistration.js` — explicit input whitelisting and preparation payload helper.
7. `dawana-platform/src/services/assistedRegistration.test.js` — five focused helper/SSR/navigation tests.
8. `dawana-platform/src/pages/Operations.jsx` — guarded existing-shell route.
9. `dawana-platform/src/services/operationsNavigation.js` — preparation destination/grouping.
10. `dawana-platform/src/services/operationsRefinement.test.js` — updated route count.
11. `scripts/validate_dic_assisted_preparation.py` — isolated no-DB/no-network runner for only these tests.
12. `scripts/DIC_2026_PHASE2_INCREMENT1.md` — this implementation and blocker report.

Pre-existing workspace changes are retained. No models, core constraints, historical migrations, price/settlement/recovery/portal services, existing participant records or staff permission groups were changed.

## Pending configuration, manual acceptance and next increment

- **Migrations:** none generated or applied. dic 0027 remains untouched. No new permission definitions or assignments were created.
- **Configuration:** existing public registration/pricing windows and payer recovery delivery must work. This task does not enable delivery workers, change Paystack credentials, start services or relax closed-registration rules.
- **Runtime/browser:** run the ten new backend checks in normal VS Code. Serve current source and test staff/nonstaff direct endpoint access, session expiry/CSRF, no-store, field errors/clear/unmount, closed registration and delivery unavailable states. Verify 1440px and 390px/360px form layout, keyboard focus and normal Operations hamburger/scrolling. No browser pass is claimed.
- **Next implementation increment:** explicitly approve a separate additive `RegistrationAssistance` schema and dedicated `can_assist_registration` permission, with actor/order/edition linkage, unique request/fingerprint and constrained retry ownership. Design known-person/current-edition duplicate resolution without fuzzy merging or editing existing identities. Then transactionally integrate the existing order-creation service, discard officer-side payer capabilities, return only a minimal assistance reference/status, and test payer recovery/checkout from a separate browser using isolated PostgreSQL and provider/delivery doubles. Preserve the paid public path and require exact target migration review excluding 0027. Do not enable staff booking creation until those tests and schema application are separately approved.

No second authentication mechanism is required. The precise unresolved requirement is **durable, constrained assisted-creation ownership/audit/idempotency**, plus approved contact delivery for independent payer recovery. This increment is a safe preparation foundation, **not a completed audited staff-assisted booking workflow**.
