from django.core.management.base import BaseCommand,CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from dic.models import CampEdition,House,TimetableEntry,CertificateRelease
class Command(BaseCommand):
    help='Read-only integrated release preflight; no storage activation or publication.'
    def add_arguments(self,p):p.add_argument('--edition',type=int,required=True)
    def handle(self,*args,**o):
        if MigrationExecutor(connection).migration_plan(MigrationExecutor(connection).loader.graph.leaf_nodes()):raise CommandError('Schema migrations are pending.')
        edition=CampEdition.objects.get(pk=o['edition'])
        self.stdout.write('Houses: '+str(House.objects.filter(edition=edition).count()))
        self.stdout.write('Published timetable entries: '+str(TimetableEntry.objects.filter(edition=edition,status='published').count()))
        config=CertificateRelease.objects.filter(edition=edition).first()
        self.stdout.write('Certificates: '+('enabled with explicit release time' if config and config.enabled and config.release_at else 'blocked until artwork, placement and exact release time approved'))
        self.stdout.write('Read-only check complete. Live R2 access and approved media rendering require separate owner-controlled verification.')
