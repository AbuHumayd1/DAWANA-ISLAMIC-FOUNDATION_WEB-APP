from dataclasses import dataclass
import re


class IsolationError(RuntimeError):
    """Only constant, non-sensitive diagnostics cross this boundary."""


def require(value, message):
    if not value:
        raise IsolationError(message)


@dataclass(frozen=True, repr=False)
class AcceptanceConfig:
    database: str
    host: str
    port: int
    app_role: str
    provision_role: str
    password: str
    secret: str

    def __post_init__(self):
        require(isinstance(self.database, str) and re.fullmatch(r'dic_2026_acceptance_[a-f0-9]{32}', self.database), 'Disposable database identity rejected.')
        require(self.host == '127.0.0.1' and type(self.port) is int and 1 <= self.port <= 65535, 'Acceptance endpoint rejected.')
        for role in (self.app_role, self.provision_role):
            require(isinstance(role, str) and re.fullmatch(r'(?:dic_)?acceptance_[a-z0-9_]{1,48}', role)
                    and not any(s in role for s in ('prod', 'live')), 'Dedicated acceptance role required.')
        require(self.app_role != self.provision_role and bool(self.password)
                and len(self.secret) >= 50 and not self.secret.startswith('django-insecure-'), 'Acceptance credentials/role separation rejected.')

    @classmethod
    def from_env(cls, env):
        require(not env.get('DATABASE_URL') and not any(env.get(k) for k in
            ('PGSERVICE', 'PGSERVICEFILE', 'PGHOST', 'PGHOSTADDR', 'PGDATABASE', 'PGPORT', 'PGUSER', 'PGPASSWORD', 'PGOPTIONS', 'PGPASSFILE')),
            'Ambient database URLs/libpq configuration are prohibited.')
        keys = ('DATABASE', 'HOST', 'PORT', 'APP_ROLE', 'PROVISION_ROLE', 'PASSWORD', 'SECRET')
        require(all(isinstance(env.get('DIC_ACCEPTANCE_' + k), str) and env['DIC_ACCEPTANCE_' + k] for k in keys),
                'Explicit acceptance configuration is incomplete.')
        values = [env['DIC_ACCEPTANCE_' + k] for k in keys]
        database, host, port, app, provision, password, secret = values
        require(re.fullmatch(r'dic_2026_acceptance_[a-f0-9]{32}', database), 'Disposable database identity rejected.')
        require(host == '127.0.0.1', 'Numeric loopback PostgreSQL host required.')
        require(re.fullmatch(r'[1-9][0-9]{0,4}', port) and int(port) <= 65535, 'Explicit PostgreSQL port rejected.')
        for role in (app, provision):
            require(re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', role) and role not in
                    ('postgres', 'dawana_app', 'root') and not any(s in role for s in ('prod', 'live')),
                    'Acceptance-only role configuration rejected.')
        require(app != provision, 'Provisioning and application roles must differ.')
        require(len(secret) >= 50 and not secret.startswith('django-insecure-'), 'Acceptance secret is insufficient.')
        return cls(database, host, int(port), app, provision, password, secret)

    def check_identity(self, observed, *, provisioning=False):
        role = self.provision_role if provisioning else self.app_role
        require(observed.get('database') == self.database and observed.get('host') == self.host
                and observed.get('port') == self.port and observed.get('role') == role,
                'Connected acceptance identity mismatch.')
        require(observed.get('superuser') is False and observed.get('createrole') is False,
                'Overprivileged acceptance role rejected.')
        if not provisioning:
            require(observed.get('createdb') is False, 'Application role must not create databases.')
        else:
            require(observed.get('createdb') is True, 'Provisioner creation privilege is not established.')

    def check_unused(self, existing_names):
        require(self.database not in existing_names, 'Existing acceptance target must never be reused or replaced.')

    def check_write_target(self, target, observed, receipt):
        self.check_identity(observed)
        require(target == self.database and receipt.get('database') == target
                and receipt.get('host') == self.host and receipt.get('port') == self.port
                and receipt.get('owner') == self.app_role and receipt.get('created_by') == self.provision_role
                and receipt.get('run_id') == self.database.removeprefix('dic_2026_acceptance_')
                and receipt.get('newly_created') is True,
                'Write/migration target lacks matching new-database ownership evidence.')
        # This validates supplied evidence only. It does not open a connection,
        # authenticate an operator, create a lease or authorize a write command.
