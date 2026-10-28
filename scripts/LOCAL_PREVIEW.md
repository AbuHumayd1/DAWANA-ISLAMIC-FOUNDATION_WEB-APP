# Desktop local preview

Run from the sole development project:

```powershell
Set-Location "C:\Users\hp\Desktop\DA'WANA WEB--APP"
.\scripts\start-local-preview.ps1
```

The script uses the existing Python virtual environment and frontend packages.
If your working Python is elsewhere, supply `-PythonExe 'C:\path\python.exe'`.
It does not install dependencies, create another workspace or contact deployment services.
Use your normal approved PowerShell script-execution policy; no policy changes are included.

## Local database preparation

The Python helper loads existing local connection settings without printing credentials.
It refuses a non-loopback host, a test database, a maintenance database, or a name
containing production/staging markers. It prints the exact host, port and database
name, checks migration/model parity and lists pending migrations, including 0021.

If migrations are pending, type the exact intended LOCAL DEVELOPMENT database name
when prompted. This confirms the target and authorizes those local migrations.
Before any migration, it makes a full custom-format pg_dump archive and verifies
its header, table of contents and complete archive readability with pg_restore
(without restoring or connecting pg_restore to a database). A missing, empty or
unreadable archive blocks migration. The backup is retained under .local-preview/.
That folder is ignored by Git because backups contain private development data.
No reset, flush, drop, data seeding, category/price changes or automatic restoration
is performed. Migrations can contain data operations, which is why the target,
plan and backup are checked first. The backup is not a tested restore rehearsal.

The script prefers pg_dump/pg_restore from the installed PostgreSQL server version:
C:\Program Files\PostgreSQL\<major>\bin. Both tools must match the server major
and each other. Inherited libpq PG* settings are cleared for the backup child;
the verified local host, port, database and user are supplied explicitly, with
the password passed only through the child environment. If necessary, supply:

```powershell
.\scripts\start-local-preview.ps1 -PgDumpPath 'C:\path\to\pg_dump.exe'
```

If the target is wrong, do not confirm it. Correct your local configuration first.
If any backup/parity/migration check fails, servers are not started. Raw connection
exceptions are suppressed. PostgreSQL tool failures report their exit code and
stderr after redacting credentials and connection URLs. Failed/partial archives
are retained and never accepted as a successful backup.
No migration has been run by Codex: Python is still inaccessible in its tool session.

## Preview URLs

- Foundation home: http://127.0.0.1:5173/
- DIC: http://127.0.0.1:5173/dic
- Media: http://127.0.0.1:5173/media
- Direct local Admin: http://127.0.0.1:8000/admin/
- Same-origin proxied Admin: http://127.0.0.1:5173/admin/
- Backend health: http://127.0.0.1:8000/api/v1/health/

Both servers bind loopback and reload edits. Existing processes on ports 8000/5173
are not killed or replaced: the script stops and asks you to identify them.
Background process IDs and separate stdout/stderr logs are retained in
.local-preview/servers.json. Do not start duplicate copies after an error.
The Django reloader can have a child PID in addition to its launcher PID.
Keep logs/backups local; do not publish them or paste unreviewed logs into chat.

The frontend uses Vite's existing /api, /admin and /static proxies to local Django.
No Netlify configuration is loaded. In child processes only, the helper selects
development settings, localhost hosts/origins, private LOCAL image/MP4 storage,
in-memory mail and Paystack test mode. A live or missing Paystack key is not used.
The on-disk .env and application payment implementation are unchanged. Real checkout
and its callback configuration are outside this visual/Admin preview task.

## DIC Admin inventory

Preparation verifies these actual runtime model registrations after migrations:

| Model | Admin path | Purpose |
|---|---|---|
| CampPhotograph | /admin/dic/campphotograph/ | Approved camp photos; mark featured for the curated six |
| PromoVideo | /admin/dic/promovideo/ | Uploaded MP4 experience/introduction clips and posters |
| Lecturer | /admin/dic/lecturer/ | Lecturer identity and portrait |
| LecturerAppearance | /admin/dic/lecturerappearance/ | Edition participation, topic, verification and publication |
| CampActivity | /admin/dic/campactivity/ | Approved programme activity cards |
| CampFlyer | /admin/dic/campflyer/ | Official flyer image and publication |
| CampVideo | /admin/dic/campvideo/ | Legacy hosted lecture/video links; not uploaded promotions |

MemoryActivity is the existing photograph categorization model, distinct from
programme CampActivity. All models remain in the DIC Django app.

An active superuser can see all controls. Ordinary staff need the relevant model
view/add/change permissions; publication uses separate publish permissions.
The script reports whether an active local superuser exists; it does not create
accounts automatically. If needed, explicitly create one securely in your terminal:

```powershell
.\backend\.venv\Scripts\python.exe scripts\local_preview.py create-admin
```

No password is placed in source, script arguments or chat.

## DIC/frontend/API mapping

| Landing content | Source |
|---|---|
| Camp information / registration | /api/v1/dic/registration-options/ |
| Flyer and bounded MP4 promotions | /api/v1/dic/editorial/ |
| Curated photographs | /api/v1/dic/memories/?curated=1 |
| Lecturer profiles and activities | /api/v1/dic/showcase/ |

The DIC landing imports DICCampInfo, DICEditorial, MemoriesGallery in compact mode,
and CampShowcase. It does not import Media.jsx or its archive/filter configuration.
Promotional MP4s have their own storage/model/stream endpoints. Existing hosted
video endpoints remain untouched and distinct.

The current Media.jsx is a separate foundation archive shell with placeholders,
including Ramadan Tafseer. There is no dedicated foundation Media Django app/model
or API connected to that page in this checkout. Do not mistake the legacy DIC
CampVideo model for a completed foundation-wide media library. This task does not
build or refactor that library.

Local preview only shows actual approved local content: new tables are empty until
editors supply it. Set the intended existing CampEdition active, publish approved
flyer/promotions/activities/lecturer appearances, and feature selected photographs
through Admin. Do not invent official programmes or import staging records.
Draft content remains private; an empty section is not proof of a broken API.
The helper does not download R2 objects; keys referencing remote-only files need
their approved local assets before images/video can render in local storage mode.

Real MP4 uploads need ffprobe on PATH or DIC_FFPROBE_BINARY set to its executable.
The page/Admin can start without it, but genuine upload validation fails closed.
Flyers/posters/photographs use the existing Pillow image normalization.

## Why Admin might look old

An onrender.com, netlify.app or deployed custom-domain URL runs deployed code,
not this Desktop checkout. Local edits do not update it. At localhost, check the
actual process working directory, this script's registration report, pending
migrations and account permissions. No particular browser's cause has been verified
without seeing its URL. No Admin redesign or deployment is part of this setup.

## Equivalent foreground starts after successful preparation

Terminal 1, repository root:

```powershell
.\backend\.venv\Scripts\python.exe -B scripts\local_preview.py serve
```

Terminal 2:

```powershell
Set-Location "C:\Users\hp\Desktop\DA'WANA WEB--APP\dawana-platform"
$env:DJANGO_API_PROXY_TARGET = 'http://127.0.0.1:8000'
$env:VITE_API_BASE_URL = '/api/v1'
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Use these instead of, not alongside, the already running startup-script processes.
