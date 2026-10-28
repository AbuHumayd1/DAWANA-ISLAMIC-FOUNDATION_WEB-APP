# Manual selective staging commits — PowerShell

Git writes are blocked in the agent session. Run these commands yourself from the repository root. This runbook is NOT part of the approved commit scope. Do not stage it.

## Preconditions

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
git branch --show-current
git rev-parse main
git diff --cached --name-only
git status --short
```

Require branch `staging/dawana-e2e`, main hash `074c49b4f8ab01914b992f59ca4125f696eb8669`, and an empty index. Stop if these differ. Do not reset/stash/discard anything.

## Commit 1

```powershell
$participantFiles = @(
  'backend/dic/models.py'
  'backend/dic/operations_api.py'
  'backend/dic/urls.py'
  'backend/dic/participant_api.py'
  'backend/dic/participant_services.py'
  'backend/dic/management/commands/setup_dic_staff_roles.py'
  'backend/dic/management/commands/send_dic_portal_messages.py'
  'backend/dic/management/commands/cleanup_dic_participant_access.py'
  'backend/dic/migrations/0014_participant_portal_and_ids.py'
  'backend/dic/migrations/0015_guard_registered_category_edition.py'
  'backend/dic/test_participant_portal.py'
  'backend/dic/test_participant_remediation.py'
  'dawana-platform/src/App.jsx'
  'dawana-platform/src/pages/Operations.jsx'
  'dawana-platform/src/pages/ParticipantPortal.jsx'
  'dawana-platform/src/pages/ParticipantPortal.css'
  'dawana-platform/src/pages/StaffParticipantIDs.jsx'
  'dawana-platform/src/services/operationsApi.js'
  'dawana-platform/src/services/operationsNavigation.js'
  'dawana-platform/src/services/participantApi.js'
  'dawana-platform/src/services/participantIdentity.js'
  'dawana-platform/src/services/apiResponse.js'
  'dawana-platform/src/services/requestScope.js'
  'dawana-platform/src/services/participantApi.test.js'
  'dawana-platform/src/services/participantRemediation.test.js'
  'MILESTONE_1L_ARCHITECTURE.md'
  'MILESTONE_1L_A_IMPLEMENTATION.md'
  'MILESTONE_1L_A_ACCEPTANCE_AUDIT.md'
  'MILESTONE_1L_A_REMEDIATION.md'
)
git add -- $participantFiles
if ($LASTEXITCODE -ne 0) { throw 'Selective staging failed; stop.' }
git add -p -- backend/config/settings/base.py
```

For the three current `base.py` hunks, answer:

1. **y** — official-logo comment and `DIC_OFFICIAL_LOGO_URL` setting.
2. **n** — DATABASE_URL/database configuration replacement.
3. **y** — the three `dic_participant_*` throttle entries.

Read the displayed content rather than relying solely on hunk numbers. If Git combines unrelated hunks, use `s` to split; stop if you cannot isolate them. This changes only the index, not the working file.

```powershell
git diff --cached -- backend/config/settings/base.py
git diff -- backend/config/settings/base.py
git diff --cached --name-only
git diff --cached --check
git diff --cached
```

The staged base.py diff must have only logo/throttles. Its unstaged diff must have the database replacement. Both migrations must appear in the staged list. Inspect the entire staged diff for secrets/excluded files before proceeding.

```powershell
git commit -m 'feat(dic): add participant portal and remediated ID lifecycle'
if ($LASTEXITCODE -ne 0) { throw 'Commit 1 failed; stop.' }
git show --format=fuller --stat HEAD
git show --format= --name-only HEAD
git show --format= HEAD
git status --short
```

## Commit 2

```powershell
$backendDeploymentFiles = @(
  '.gitattributes'
  'backend/config/settings/base.py'
  'backend/config/settings/staging.py'
  'backend/config/staging_email.py'
  'backend/config/staging_logging.py'
  'backend/config/tests.py'
  'backend/requirements.txt'
  'backend/constraints-staging.txt'
  'backend/gunicorn.conf.py'
  'backend/render-build.sh'
  'backend/render-start.sh'
  'backend/render-migrate.sh'
  'backend/staging.env.example'
  'backend/health/views.py'
  'backend/health/tests.py'
  'RENDER_STAGING_PREPARATION.md'
)
git add -- $backendDeploymentFiles
if ($LASTEXITCODE -ne 0) { throw 'Selective staging failed; stop.' }
git diff --cached -- backend/config/settings/base.py
git diff --cached -- backend/staging.env.example
git diff --cached --name-only
git diff --cached --check
git diff --cached
```

base.py must now contain only its remaining database hunk. Environment examples must contain placeholders/empty secret fields only, never real DATABASE_URL, keys or passwords.

```powershell
git commit -m 'feat(deploy): prepare Render staging backend'
if ($LASTEXITCODE -ne 0) { throw 'Commit 2 failed; stop.' }
git show --format=fuller --stat HEAD
git show --format= --name-only HEAD
git show --format= HEAD
git status --short
```

## Commit 3

```powershell
$frontendDeploymentFiles = @(
  'dawana-platform/package.json'
  'dawana-platform/scripts/build-staging.mjs'
  'dawana-platform/scripts/staging-config.mjs'
  'dawana-platform/src/services/stagingConfig.test.js'
  'dawana-platform/staging.env.example'
)
git add -- $frontendDeploymentFiles
if ($LASTEXITCODE -ne 0) { throw 'Selective staging failed; stop.' }
git diff --cached --name-only
git diff --cached --check
git diff --cached
```

Only these five files may be staged. No homepage/theme changes or generated proxy output.

```powershell
git commit -m 'feat(deploy): add isolated staging frontend build'
if ($LASTEXITCODE -ne 0) { throw 'Commit 3 failed; stop.' }
git show --format=fuller --stat HEAD
git show --format= --name-only HEAD
git show --format= HEAD
git status --short
```

## Validation after all three commits

Use the existing local development settings and separate PostgreSQL TEST database. Never run these tests with Render/live DATABASE_URL values. Do not run `migrate` against the application DB; application 0015 is intentionally pending.

```powershell
Push-Location backend
try {
  & .\.venv\Scripts\python.exe manage.py test --keepdb --noinput
  if ($LASTEXITCODE -ne 0) { throw 'Django tests failed.' }
  & .\.venv\Scripts\python.exe manage.py check
  if ($LASTEXITCODE -ne 0) { throw 'Django checks failed.' }
  & .\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
  if ($LASTEXITCODE -ne 0) { throw 'Migration drift check failed.' }
  & .\.venv\Scripts\python.exe manage.py showmigrations dic
  & .\.venv\Scripts\python.exe manage.py migrate --plan
  & .\.venv\Scripts\python.exe manage.py shell -c 'from django.db import connection; from django.db.migrations.loader import MigrationLoader; MigrationLoader(connection).check_consistent_history(connection); print("Migration history consistent")'
  if ($LASTEXITCODE -ne 0) { throw 'Migration history check failed.' }
} finally { Pop-Location }

Push-Location dawana-platform
try {
  npm.cmd test
  if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed.' }
  npm.cmd run lint
  if ($LASTEXITCODE -ne 0) { throw 'Frontend lint failed.' }
  npm.cmd run build
  if ($LASTEXITCODE -ne 0) { throw 'Frontend production build failed.' }
  node --input-type=module -e "import {spawnSync} from 'node:child_process'; const result=spawnSync(process.execPath,['scripts/build-staging.mjs'],{stdio:'inherit',env:{...process.env,DAWANA_STAGING_FRONTEND:'true',SITE_ID:'isolated-local-build',DAWANA_STAGING_SITE_ID:'isolated-local-build',STAGING_BACKEND_ORIGIN:'https://dawana-staging-test.onrender.com',VITE_API_BASE_URL:'/api/v1'}});process.exit(result.status ?? 1);"
  if ($LASTEXITCODE -ne 0) { throw 'Staging build failed.' }
  Get-Content dist/_redirects
  npm.cmd run build
  if ($LASTEXITCODE -ne 0) { throw 'Restoring normal build output failed.' }
  Get-Content dist/_redirects
} finally { Pop-Location }

git diff --check
git branch --show-current
git rev-parse main
git rev-list --count main..HEAD
git log --reverse --format='%h %s' main..HEAD
git diff --cached --name-only
git status --short
```

Require exactly 3 new commits, staging branch unchanged, main still `074c49b4f8ab01914b992f59ca4125f696eb8669`, and empty index.

The old venv executable may be unavailable on this workstation. If so, use this established equivalent from backend/ for each manage.py command, replacing the argv list appropriately; it uses the same installed project packages:

```powershell
& 'C:\Program Files\PostgreSQL\17\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.venv/Lib/site-packages'); sys.path.insert(0,'.'); sys.argv=['manage.py','test','--keepdb','--noinput']; runpy.run_path('manage.py',run_name='__main__')"
```

Expected excluded changes after commits:

```text
 M dawana-platform/public/appearance.js
 M dawana-platform/src/services/appearance.test.js
?? .vscode/
?? MILESTONE_1K_GIT_STATUS.txt
?? THEME_GIT_STATUS.txt
?? VISUAL_REGRESSION_RESTORATION.md
?? acceptance-artifacts/
?? MANUAL_STAGING_COMMITS.md
```

Ignored .env, node_modules, dist, staticfiles, virtualenvs/caches and generated outputs must stay excluded. Existing environment examples are safe only while they retain placeholder values. Do not push or deploy. Gunicorn/WhiteNoise Linux runtime validation remains outstanding as documented in the staging guide.
