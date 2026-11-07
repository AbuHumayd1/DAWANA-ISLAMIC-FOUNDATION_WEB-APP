# Production remediation — source changes, not launch acceptance

## Local verification evidence for this working patch

Frontend: node --test --test-reporter=spec src/services/*.test.js completed
234 tests: 234 passed, 0 failed, 0 skipped, 0 cancelled (22.34 seconds).
The first run had one obsolete inline-payload source assertion; it was updated
to require the validated extracted helper. JSX parsing of DIC.jsx and main.jsx
using Vite transformWithOxc passed. Git diff --check passed.

Python execution is unavailable in this terminal: both `python` and the supplied
Python313 executable path were reported as unrecognized commands. No Python
syntax check or backend test is claimed. No environment repair was attempted.
New backend tests are discoverable by the existing core partition; two new pure
test classes are also included in the database-free policy suite. Actual backend
acceptance requires all nine GitHub Actions jobs on the future reviewed commit.
No workflow file was modified. Gateway syntax/runtime and actual browser error
boundary lifecycle have not been tested by these service/JSX checks.

The patch contains 24 modified tracked files and 15 new source/test/documentation
files. The index is empty. All 73 pre-existing untracked paths were checked by
SHA-256 and remained unchanged; current untracked total is 88.

Baseline: staging/dawana-e2e at 4afe364df0df8cdf910efceb96099b506ecb02f0.
The nine-job green run 42363315629 and 229 frontend tests are HISTORICAL baseline
evidence, not results for this patch. No finding is closed by infrastructure
assumption. Provider, domain, paid services and live collection remain unapproved.

## Findings and gates

| ID | Source correction / retained boundary | Remaining acceptance |
| --- | --- | --- |
| R01 BLOCKER | Production Vite builds reject API bases other than /api/v1; existing origin/grant/CSRF checks retained. Direct-edge Nginx template reserves API/admin/static/media/health paths. | Owner-approved gateway, actual ingress, TLS, browser callback and cookie acceptance. |
| R02 HIGH | Initial and uncertain retry/resume use the same complete validated submission; credentials remain memory-only. Refresh removes PII and directs to existing verified recovery. | Backend CI, browser interruptions/expiry/foreign-account acceptance. |
| R03 HIGH | Shared generic settlement evidence for Housing and Finance: configured mode, production live-only, amounts, currency, revision, timing and provider identity. Housing rejects conflicting/reconciliation attempts and rechecks under source locks. Finance retains excluded rows and provider mode. | Both PostgreSQL versions; historical reporting, locking and scale tests. Tutor entitlement remains separate and unchanged. |
| R04 HIGH | Existing reconcile/amount-mismatch exclusions preserved; no automatic policy change or historical record deletion. | OWNER POLICY APPROVAL REQUIRED; see below. |
| R05 HIGH | Offline build gate requires Python 3.13, Django 5.2.18, PDF libraries, Liberation fonts and executable ffprobe. Builds still never initialize data/migrate. | Actual immutable image, Linux font bounds, binary provenance, media/PDF acceptance. |
| R06 HIGH | Production admin POST login uses existing durable recovery counters, verified IP/account pair, separate IP ceiling and fail-closed database failure. Django authentication/staff/permissions remain active. | Real admin login regression CI; infrastructure MFA/access restriction and recovery procedure. |
| R07 HIGH | Recovery worker suppresses stale uncertain sends rather than resending; bounded batch <=100. Aggregate queue health command and scheduler template provided. Existing portal claims/skip_locked retained. | Scheduler availability, TTL/capacity, concurrency/SMTP and alert acceptance. Housing worker remains development-only. |
| R08 HIGH | Synchronous exports bounded at 25 submitted IDs; validation outside transaction, issuance/revocation locks and audits retained during generation. | Lock duration still includes media/PDF. Load/concurrency measurements required before capacity claims or higher limits. |
| R09 HIGH | Migration manifest now binds configured host/port/role and server-reported cluster identity; wrong endpoint refused before connection. | Managed provider must permit pg_control_system inspection by approved operator; independent identity approval and backup evidence required. |
| R10 HIGH | No authority grants or edition assignment policy introduced. Restricted administrators still lack can_manage_registration_access. | OWNER POLICY APPROVAL REQUIRED. |
| R11 BLOCKER | Provider-neutral managed target and validated explicit bind address/port; self-managed loopback and Render compatibility retained. | All actual host/DB/cache/R2/DNS/HTTPS/static/worker configuration unverified. |
| R12 BLOCKER | No recovery claims or key changes made. | Independent DB/R2/source/key restore, RPO/RTO, retention, incident owners and rehearsal evidence. |
| R13 BLOCKER for live collection | No activation, credentials or settlement changes. | Official merchant/FCMB settlement confirmation; approved live end-to-end acceptance. |
| R14 HIGH | One verified immediate gateway replaces client IP; arbitrary forwarded chains removed; DRF uses REMOTE_ADDR. Unknown headers never establish identity. | Prove real ingress overwrites headers and restricts backend network access. |
| R15 MEDIUM | Runtime parity gate and portable system requirements explicit. No speculative dependency upgrades. | Full transitive dependency lock and immutable base-image digest still pending; existing constraints are not a complete lock. |
| R16 MEDIUM | Saved regular-registration drafts contain metadata only, not contact/participant details, passwords, bearer tokens, checkout URLs or provider references. Legacy draft PII scrubbed on load. | Shared-device/browser acceptance; unsent forms intentionally do not survive refresh. Order IDs remain sensitive metadata. |
| R17 MEDIUM | Global React boundary offers accessible generic recovery without logging exception contents or claiming payment success. | Actual browser render failure, chunk failure, keyboard/mobile and accessibility acceptance. |
| R18 LOW | Current provider-neutral plan supersedes archived historical deployment instructions/results. | Owner review and reconciliation after provider selection. |

## Same-origin contract and proxy trust

One public HTTPS origin serves the frontend and /api/v1. Paystack callback:
/dic/register/payment-return; webhook: /api/v1/dic/payments/paystack/webhook/.
Neither callback parameters nor a transaction reference authorize a booking.
Do not remove paymentReturnApi.js's origin guard or grant checks.

Use VITE_API_BASE_URL=/api/v1. CORS/CSRF use exact approved HTTPS origins;
cookies stay secure. Never use wildcard trusted origins. The production build
rejects cross-origin API configuration. Staging configuration remains historical.

ops/production/gateway.nginx.conf.example is a DIRECT TLS EDGE template, not a
managed-ingress prescription or installed configuration. Replace invalid domain,
certificate paths and frontend root only after approval. It overwrites forwarded
headers using its socket peer and proxies only to loopback. No direct raw media
filesystem is served. API/admin responses must never be cached by gateway/CDN.

Set DAWANA_TRUSTED_GATEWAYS to exact verified immediate gateway CIDRs only
(e.g. local /32 for the direct-edge template). Trusted gateways MUST strip client
supplied X-Dawana-Client-IP and replace it with one verified address, not a chain.
Missing/malformed verified client addresses fail closed. Forwarded-For is removed;
DRF NUM_PROXIES=0 and custom throttles consequently use the same REMOTE_ADDR.
Untrusted peers cannot supply trusted client IP or forwarded HTTPS scheme.
DJANGO_TRUST_PROXY_HTTPS may be enabled only after ingress verification.
Gunicorn's default forwarded trust remains loopback-only; no wildcard expansion.
The backend must be network-restricted to this gateway. A provider whose ingress
cannot meet this contract needs a separately reviewed adapter, not blind trust.

Managed hosting: DJANGO_DEPLOYMENT_TARGET=managed requires explicit
DJANGO_BIND_ADDRESS (127.0.0.1 or 0.0.0.0). PORT or DJANGO_BIND_PORT must be a
valid port. Wildcard is authorized only for a verified private platform ingress.
Self-managed defaults to 127.0.0.1:10000; optional DJANGO_BIND_PORT is validated.
Render's established default remains supported. No provider-name alias disables
security. PostgreSQL always requires verify-full and hostname/CA validation.

## Refund/reversal decision — OWNER POLICY APPROVAL REQUIRED

Current charge.success webhook and immutable finance reconciliation/adjustment
history do not constitute a refund lifecycle engine. Reconciliation adjustments
are bounded and audited; their existing duplicate controls must remain active.
A finance note alone does not revoke sessions, IDs or housing. Entitlement checks
already deny unpaid/refunded/cancelled orders and unresolved settlement states;
new generic settlement checks never mutate those records or revoke old access.

The owner must specify, separately for FULL REFUND, PARTIAL REFUND, CHARGEBACK,
REVERSAL and PENDING DISPUTE:

| Decision dimension | Approval needed |
| --- | --- |
| Registration | Retain, suspend, cancel or review; effective time and appeal. |
| Housing | Retain/hold/release and treatment of already occupied spaces. |
| Participant sessions | Revalidate only, suspend or explicit revocation. |
| Cards/QR | Keep, hold or revoke; treatment of previously printed credentials. |
| Authority | Named Finance/registration decision makers and separation of duties. |
| Audit | Provider event identity, amount, evidence, actor, approval, before/after state and idempotency key. |

Consumers include password/OTP booking scopes, participant portal, enrollment,
ID issue/read/QR verification, check-in/movement and housing allocation, plus
Finance reporting. A future policy service must coordinate these consumers with
existing locking and immutable financial history. Do not implement automatic
revocation based solely on a new reconciliation note without policy approval.

## Staff edition decision — OWNER POLICY APPROVAL REQUIRED

Current active staff permissions are global; edition query filters choose data,
not authority. Option 1 explicitly approves global committee access, with audited
role provisioning and least privilege. Option 2 authorizes a separately designed
staff-to-edition assignment model, enforcement on every route/export and
cross-edition negative tests. No assignments or grants were added by this sprint.
Restricted DIC Administrators remain without can_manage_registration_access.

## Runtime and operations

Use Python 3.13 and the existing requirements.txt + constraints-staging.txt
(historical filename). These are not a complete transitive lock. On an approved
Linux image install fonts-liberation (or fonts-liberation2 providing the checked
paths) and ffmpeg/ffprobe. The existing checksum-pinned optional ffprobe helper is
retained. Never silently skip media validation. Node 22.19.0 matches local test
execution; verify the actual image satisfies the locked Vite engine requirement.
Pin image digest and resolved dependencies before accepting reproducibility.

Production build remains bash backend/production-build.sh; start remains
bash backend/production-start.sh. No migration/seed/cache creation in either.
python -m config.runtime_requirements performs offline runtime checks.

Delivery scheduling template: ops/production/delivery.cron.example. Once
separately authorized, execute each bounded delivery command every minute and
queue health every minute, with alerts at oldest live queued age >90 seconds.
Validate throughput against the ten-minute recovery code expiry; a schedule
alone does not prove delivery capacity. Suppressed uncertain sends require a
fresh user challenge, never automatic provider retry. Use separate overlap locks
and shared database claims. Cleanup may run hourly after authorization; it removes
expired access/recovery records, never R2 objects. No automatic object cleanup.
Monitor queue age, failures/suppression, missed scheduler ticks and provider health
without destinations, tokens, codes, participant details or request URLs in logs.

Fresh production only: no demo database or portraits transferred. Housing worker
production refusal remains intact; no scheduler entry is provided for it.

## Migration approval and release order

All following database/infrastructure operations require separate owner approval
and must NOT be executed by build/start/this sprint. Plan inspection connects to
the target and therefore also needs target-access approval.

1. Select provider, domain, topology, refund/staff policies, capacity and budget.
2. Review this patch; authorize exact-path publication and run all nine CI jobs.
3. Verify provider ingress, TLS, runtime assets, cache, secrets, R2 and monitoring.
4. Provision a fresh empty approved PostgreSQL target with restricted app role
   and separate migration operator. Never use dawana_dev/dic_2026_demo.
5. Independently record endpoint, port, migration role and PostgreSQL system
   identifier. The inspection role needs narrowly approved pg_control_system()
   access; lack of access blocks, rather than bypasses, cluster identity checks.
6. Run release_migrations only with explicit --database-name NAME --hostname HOST
   --port PORT --role ROLE --cluster-id IDENTIFIER; export with --manifest-file.
   Review exact migration source hashes/order/target identity and backup/restore
   evidence. Existing approval files without target identity must be regenerated.
7. After separate approval use --approval-file FILE --apply-approved-plan with
   the identical target arguments. Create cache table and initial administrator
   only through separately approved commands. Never embed passwords in commands.
8. Independently rehearse restores including DB, R2, Django SECRET_KEY-derived ID
   credentials, recovery encryption key and source. No production overwrite drill.
9. Verify same-origin deep links, reserved routes, hostile headers, secure cookies,
   CSRF, private media, login limits, callback/webhook and uncertain checkout.
10. Final exact-SHA CI and owner deployment acceptance; live payments and opening
    registration require additional explicit approval and owner-supplied dates.

Preserve approved fees, the intentional 17-year-old classification and tutor
exemption. Email/password only. Donations, Google sign-in and deferred games stay
disabled. R11/R12/R13 and browser/load/provider acceptance remain release gates.
