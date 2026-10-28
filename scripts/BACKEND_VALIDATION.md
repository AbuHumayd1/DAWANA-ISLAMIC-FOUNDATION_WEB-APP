# One-command local DIC backend validation

Run only from the sole Desktop project. Existing work, stash and backup stay intact.
The scripts are prepared but NOT executed by Codex: its Python launch is denied.
No claim of backend PASS or staging readiness is made until the JSON says PASS.

## Execute in your working PowerShell

    Set-Location "C:\Users\hp\Desktop\DA'WANA WEB--APP"
    .\scripts\validate-dic-backend.ps1 -InstallFfprobe

The optional switch installs the free portable Gyan.FFmpeg package through WinGet,
scoped to the current Windows user; no administrator/system fallback or paid service.
WinGet's package manifest includes both ffmpeg and ffprobe and download hashes.
No source files, package dependencies, database privileges or hosting settings are
changed by this installation. Do not weaken a centrally managed PowerShell policy;
if scripts are blocked, use your normal approved script-execution process.

If already installed, omit -InstallFfprobe or supply:
    .\scripts\validate-dic-backend.ps1 -FfprobePath 'C:\path\to\ffprobe.exe'
An alternative working Python may be selected with -PythonExe. The existing venv
is tried first, then python.exe and the Python 3.13 launcher. No Python reinstall.
No credentials are arguments and the script never asks you to paste secrets.

## What the single run does
1. Verify Python and already-installed dependencies (does not reinstall).
2. Read backend/.env in the child process without printing values. Refuse any DB
   host except loopback localhost/127.0.0.1/::1. Use your existing local role/port.
3. Inspect test_dawana_dev with default_transaction_read_only=on: report existence,
   visible table count and Django migration record count only. No participant,
   payment or other row contents are exported. It is never reused for tests.
   Lack of read/CREATEDB permission stops safely; no permission changes are made.
4. Configure isolated development settings in child memory: default database is
   the local maintenance postgres DB, test DB has a fresh UUID name, Paystack keys
   are synthetic test keys, recovery mail is in-memory, media is temporary/local.
   No .env or existing DB settings are written. R2/AWS credentials are synthetic.
5. Run Django system checks and MigrationLoader/Autodetector against all migrations,
   including DIC 0021. No makemigrations output or application DB writes occur.
6. CREATE a unique test_dawana_validation_<timestamp>_<UUID> database. The name is
   generated inside the runner and checked absent. It cannot be user-selected.
   No DROP DATABASE, reuse, --noinput or overwrite of existing test databases.
7. Run requested promotions/memories/videos/showcase, registration, payment,
   concurrent settlement, client and staging-tester tests. Migrations/data/flushes
   run only inside that new test database. DiscoverRunner uses keepdb=True; the
   new database is RETAINED after success or failure. Repeated invocations create
   additional databases; review the first result before rerunning.
8. Deny external Python socket connections during tests. No real R2/Paystack calls.
9. Use ffmpeg to generate a one-second synthetic H.264 MP4; validate it with real
   ffprobe and exercise private LOCAL MP4 storage save/open/byte equality. No
   participant video is needed. No uploaded object or remote operation is involved.
10. Write validation-results/<run>.json and a secret-redacted test log. These are
    local untracked reports; inspect before sharing/committing. Real credential
    values and arbitrary exception tracebacks are not exported. A failing check
    identifies phase/class; validation failures appear in the redacted test log.

## Expected result
JSON result PASS requires matching migration states, zero focused-test failures,
and genuine MP4 validation/local round trip. FAIL/BLOCKED or a missing ffprobe
check is not a staging deployment pass. Retain the generated database for inspection;
cleanup would require separate authorization naming that exact database.
The script has no cleanup/drop code. It creates no Git repositories/workspaces,
branches or commits; it does not run frontend checks, push or deploy.

A read-only inspection cannot prove the existing test_dawana_dev is disposable;
that is precisely why it is left intact. The new database needs your existing
local role to have CREATEDB. Do not supply a production/staging account as a fix.
Actual staging R2 connectivity and Netlify/Render byte-range delivery still require
separate authorized staging checks; mocked SDK tests are not a real R2 test.

References:
https://www.gyan.dev/ffmpeg/builds/
https://github.com/microsoft/winget-pkgs/blob/master/manifests/g/Gyan/FFmpeg/8.1/Gyan.FFmpeg.installer.yaml
