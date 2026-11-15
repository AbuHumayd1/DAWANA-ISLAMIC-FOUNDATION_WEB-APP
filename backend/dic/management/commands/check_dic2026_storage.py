"""No secrets printed, no object mutations, no activation."""
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from django.core.exceptions import ImproperlyConfigured
from dic.storage_configuration import production_storage
class Command(BaseCommand):
    help='Validate both approved private R2 boundaries. No network, writes or activation.'
    def handle(self,*args,**options):
        try:
            media=production_storage(settings,'media');private=production_storage(settings,'private')
            if media['aws_access_key_id']==private['aws_access_key_id']:raise ImproperlyConfigured('Independent credentials required.')
        except ImproperlyConfigured:raise CommandError('Storage configuration incomplete or invalid; review approved buckets, HTTPS R2 endpoint, auto region and independent credentials. Values are never printed.') from None
        self.stdout.write('Both private bucket configurations valid. No network, activation or portrait cutover performed.')
