# DIC 2026 navigation, fee presentation and registration privacy

## Implemented UI changes

- Removed Registration preparation from the shared Operations navigation and Participants & Registration group. No additional corresponding shortcuts were found in CampsiteFoundation, campsiteModules or Operations components.
- `/dic/operations/assisted-registration` now redirects with history replacement to `/dic/operations/registrations`. This route remains inside the existing Operations authentication gate: session loading and login are rendered before protected routes. Registrations keeps its existing API permissions. The assistance page source and all backend infrastructure, migration, permission and audit code are retained.
- Public `/dic` camp information now displays **Registration fees**, **Based on participant category**, and **View applicable fees and early-bird rates during registration.** No actual price is hardcoded or changed.

Previous range source: DICCampInfo called `campFeeRange(options.categories)`, which maps `categoryFee` over backend `current_fee_ngn`, then takes min/max. Registration options come from the existing public DIC options endpoint; RegistrationCategorySerializer computes current fees with `price_for_category(category, timezone.now())`. That configuration, category pricing helper, fee estimation, early-bird logic and checkout are unchanged. The obsolete range utility remains available without affecting registration.

## Focused verification executed

- 16 focused frontend checks passed (Operations refinement, assistance helpers/navigation and DIC presentation utilities).
- Affected-file oxlint passed.
- Production build passed; existing bundle-size warning remains.
- Server-side React rendering of DICCampInfo passed in loading, error and ready states: all three requested strings are present, former label and numeric fee range absent.
- Targeted Git whitespace checks passed (normal line-ending notice only).
- Authentication-before-redirect ordering verified through source inspection. No live-browser/auth-session pass is claimed. Manual check: signed out, visit the former URL and confirm existing Operations login; sign in with existing authorized account and confirm redirect to Registrations. Verify sidebar and homepage at desktop/phone widths.

No backend check or database operation was necessary for these UI changes. No public registration form, price configuration, Paystack activation, assisted-booking activation or operational records changed.

## Exact changed files

1. `dawana-platform/src/services/operationsNavigation.js`: remove sidebar/group destination.
2. `dawana-platform/src/pages/Operations.jsx`: authenticated redirect; remove unused assistance-page import.
3. `dawana-platform/src/components/dic/DICCampInfo.jsx`: requested fee copy; remove range-formatting usage.
4. `dawana-platform/src/services/operationsRefinement.test.js`: navigation count returns to 16.
5. `dawana-platform/src/services/assistedRegistration.test.js`: assert removed route is absent for both staff capabilities.
6. `scripts/DIC_2026_UI_AND_REGISTRATION_PRIVACY_REVIEW.md`: evidence and privacy blocker.

## Additional privacy/optional measurement request: inspected, not implemented

The user clarified that the appended adult privacy and optional-measurement request is intentional. Inspection establishes a core migration blocker, so the working public form has not been changed to accept data that current schema cannot store. No migration file was created or applied for this request.

`dic.Participant.date_of_birth`, `height_cm`, `weight_kg` are currently non-null. Supporting-app tables cannot make them nullable. The current dic migration leaf is postponed `0027_feedback_welfare`, whose parent is `0026_house_score_transaction`. A normal core successor pulls in 0027; a parallel 0026 child produces competing dic leaves, and a merge again requires 0027. Do not conceal core changes in another app, rewrite historical migrations, fake state or generate an unsafe sibling as a workaround. This is the same core migration-lineage gate documented in the Phase 2 architecture plan.

Affected source inspected:

- `backend/dic/models.py`: non-null fields, positive measurement constraints, immutable order snapshot `.isoformat()`/string conversions.
- `backend/dic/serializers.py`: required exact DOB and positive precision-limited measurements; future DOB rejection.
- `backend/dic/views.py`: exact age used against category minimum/maximum at registration date.
- `backend/dic/housing_policy.py`: exact housing-reference age and grouping; guardian/dependent decisions; missing DOB currently cannot be evaluated.
- `backend/dic/housing_models.py`, `housing_service.py`: guardian checks, date ordering and housing balance rules.
- `backend/dic/identity_admin.py`, `participant_api.py`, `identity_cards.py`: age-dependent display, dependent card and housing consumers.
- `backend/dic/operations_api.py`: DOB serialization currently calls `.isoformat()` unconditionally; missing measurements currently would stringify as `None`.
- `backend/dic/admin.py`: participant field administration.
- `dawana-platform/src/pages/DIC.jsx`: required inputs, stored draft and payload mapping, multi-camper summary, checkout/recovery; currently no adult evidence mode.
- `dawana-platform/src/pages/Operations.jsx`: participant DOB display.

Required coherent implementation after lineage resolution: nullable measurement fields retaining positive/precision validation for supplied values; explicit nullable-aware snapshots/API displays; blank-to-null frontend serialization and optional labels/help. Adult-withheld DOB requires explicit adulthood assertion/provenance and reference date, conditional DB/API validation (missing DOB allowed only for adult mode), minor DOB required and exact-adult DOB validation. Do not infer adulthood from academic status or invent a date/age. Registration category bounds require conservative proof from the adult range or controlled review; an 18+ assertion cannot prove a category maximum or any minimum above 18. Housing ages use a different reference date; unverified/insufficient evidence must fail closed for age-sensitive allocation/guardian actions, without crashes or guessed ages. Historical DOBs/snapshots remain untouched.

Focused tests still required for this unimplemented feature: minor and exact-adult DOB, adult withholding, future/contradictory DOB, category threshold/reference boundaries, guardian/housing review behavior, every optional measurement combination, null/blank/zero/negative/nonfinite/precision limits, snapshots and admin/Operations display, multi-camper public registration compatibility and unchanged trusted-payment/QR eligibility. No such feature tests or migration success are claimed.

A migration-lineage decision was requested before altering core models. The subsequent read-only findings are documented in `DIC_2026_MIGRATION_LINEAGE_REVIEW.md`: development is directly verified, six older local validation DBs already have 0027 applied, and a conditional Django `run_before` alternative is evaluated. No migration resolution is implemented. Database application is not requested or authorized by this report.
