# DA'WANA full application release

Follow [ZEVCLOUD_SIMPLE_DEPLOYMENT.md](ZEVCLOUD_SIMPLE_DEPLOYMENT.md).

The recommended path is a React static site, a native Django/Gunicorn API/Admin,
the existing PostgreSQL 18 and a persistent native worker. This is the full
application. Old combined-container guides remain under ops/container for rollback.
CI and documented release acceptance remain required. No deployment, production
access/migration, DNS change or live payment activation occurred.
