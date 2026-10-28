from django.db.backends.postgresql.base import DatabaseWrapper as PostgreSQLWrapper
from acceptance_bootstrap.runtime import deny


class DatabaseWrapper(PostgreSQLWrapper):
    def ensure_connection(self):
        deny()

    def get_new_connection(self, conn_params):
        deny()
