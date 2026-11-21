# DAWANA Media Studio 0048 — guarded production release

This change introduces the three carousel tables. It is NOT a signal that
production has been migrated or that the new runtime may be promoted.

## Confirm before applying

1. Complete CI and review the exact `dic.0048_studio_carousels` migration source.
2. Confirm the target is DAWANA production PostgreSQL, not a development copy.
   The migration runner checks the existing pinned `dawana_db`,
   `dawana_db_user`, database cluster ID, full TLS connection and release SHA.
3. Obtain a **fresh** custom-format production PostgreSQL backup. Verify archive
   readability, checksum and recoverability; keep the archive private and outside
   the source repository. The existing 0047 backup is **not** accepted.
4. Review the pending migration plan. Only `dic.0048_studio_carousels`
   may remain pending; any unrelated migration aborts.
5. After explicit owner approval, replace
   `APPROVED_FRESH_BACKUP_SHA256 = 'UNSET_PENDING_FRESH_0048_BACKUP'`
   in `backend/config/studio_0048_migration.py` with the independently
   verified SHA-256, and re-run CI to confirm the exact release commit.
6. The one-time Render build gate is activated only by
   `DAWANA_0048_APPROVAL=APPROVE-DAWANA-CAROUSELS-0048`,
   `DAWANA_0048_FRESH_BACKUP_SHA256=<verified SHA-256>` and
   `DAWANA_0048_ARCHIVE_READABLE=yes`.
   These variables must be set only for the migration build on the intended
   production service, with its current Render deployment configuration.
7. Trigger the approved one-time build. The runner checks migration SHA,
   permitted operations, production identity and schema absence; applies
   exactly 0048 in a transaction; checks all three new tables, Django
   migration record and twelve model permissions.
8. The build **must fail intentionally even after a successful migration**.
   Do not interpret an unsuccessful build as proof of a committed transaction.
   Verify the production migration record and schema independently and read-only.
9. Remove all three temporary 0048 approval variables. Allow/trigger the
   normal Render build; its preexisting read-only readiness guard must pass
   before the new backend can become live. Confirm Render's live commit.
10. Verify Cloudflare's live frontend commit and perform authorized media
    publication checks, draft invisibility, video and soundtrack tests. The
    private camper recording authorization remains unchanged.

## Fail-closed guarantees

- No `manage.py migrate` shortcut.
- No 0048 application during an ordinary build.
- No production migration without freshly pinned backup evidence and matching
  environment approval.
- No broad migration plan, data backfill or overwrite of existing media.
- No candidate runtime promotion while the guarded migration build runs.
- No automatic deletion of any media bytes.

The exact procedure may be adapted only after reviewing the resulting code and
re-running all tests. Production actions require verified workspace/service
identity and the owner's release approval.
