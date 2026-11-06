"""Explicitly invoked copy primitive. No CLI, credentials, ORM, deletion or SDK clients.

An owner must establish the source identity and supply an inventory and scoped
clients during separately approved maintenance. Importing this module does no IO.
"""
import base64
import hashlib
from collections import Counter
from botocore.exceptions import BotoCoreError, ClientError

MAX_BYTES = 12 * 1024 * 1024
DESTINATION = 'dawana-production-private'


class CutoverStopped(Exception):
    def __init__(self, report):
        self.report = report
        super().__init__('Portrait copy stopped; review the sanitized object report.')


def portrait_inventory(referenced_keys):
    """Input: portrait names only, never names/contact details or enrollment IDs.

    Output contains exact keys for a restricted manifest; do not publish it.
    No trimming, renaming or normalization of database keys is permitted.
    """
    keys = Counter(key for key in referenced_keys if key)
    if any(not isinstance(key, str) or len(key) > 200 for key in keys):
        raise ValueError('Invalid inventory; no copy attempted.')
    return [{'key': key, 'references': count} for key, count in sorted(keys.items())]


def _read(client, bucket, key, *, etag=None):
    options = {'IfMatch': etag} if etag else {}
    result = client.get_object(Bucket=bucket, Key=key, **options)
    body = result['Body']
    try:
        data = body.read(MAX_BYTES + 1)
    finally:
        body.close()
    if not data or len(data) > MAX_BYTES or result.get('ContentLength') != len(data):
        raise ValueError('size_mismatch')
    # Compare a provider checksum only when declared a full-object SHA-256.
    checksum = result.get('ChecksumSHA256')
    if checksum and result.get('ChecksumType', 'FULL_OBJECT') == 'FULL_OBJECT':
        if checksum != base64.b64encode(hashlib.sha256(data).digest()).decode('ascii'):
            raise ValueError('checksum_mismatch')
    return data


def copy_portraits(inventory, source, destination, *, source_bucket,
                  destination_bucket, maintenance_approved=False, writers_suspended=False):
    """Exact-key, create-only copy; stop on first error and return/attach a report.

    SHA-256 of downloaded source AND destination bytes is authoritative; ETag is
    only a source version condition, never presumed to be an MD5 checksum.
    Reports contain key digests instead of raw keys. There is no delete operation.
    """
    if (maintenance_approved is not True or writers_suspended is not True
            or not isinstance(source_bucket, str) or not source_bucket
            or source_bucket == destination_bucket or destination_bucket != DESTINATION):
        raise ValueError('Approved maintenance, suspended writers and explicit distinct buckets are required.')
    # Validate the complete supplied manifest before any provider access.
    inventory = tuple(inventory)
    if any(not isinstance(row.get('key'), str) or not row['key'] or len(row['key']) > 200
            or not isinstance(row.get('references'), int) or row['references'] < 1 for row in inventory):
        raise ValueError('Invalid inventory; no copy attempted.')
    report = []
    for row in inventory:
        key = row['key']
        entry = {'key_digest': hashlib.sha256(key.encode('utf-8')).hexdigest(),
                 'source_bucket': source_bucket, 'destination_bucket': destination_bucket}
        try:
            info = source.head_object(Bucket=source_bucket, Key=key)
            data = _read(source, source_bucket, key, etag=info['ETag'])
            if info.get('ContentLength') != len(data):
                raise ValueError('size_mismatch')
            existed = True
            try:
                previous = _read(destination, destination_bucket, key)
            except ClientError as error:
                if str(error.response.get('Error', {}).get('Code')) not in ('NoSuchKey', '404', 'NotFound'):
                    raise
                existed = False
            if existed:
                if previous != data:
                    raise ValueError('destination_conflict')
            else:
                destination.put_object(Bucket=destination_bucket, Key=key, Body=data,
                    ContentLength=len(data), ContentType='image/jpeg', IfNoneMatch='*')
            verified = _read(destination, destination_bucket, key)
            if len(verified) != len(data):
                raise ValueError('size_mismatch')
            checksum = hashlib.sha256(data).hexdigest()
            if hashlib.sha256(verified).hexdigest() != checksum:
                raise ValueError('checksum_mismatch')
            head = destination.head_object(Bucket=destination_bucket, Key=key)
            if head.get('ContentLength') != len(data):
                raise ValueError('size_mismatch')
            entry.update(status='verified_existing' if existed else 'copied_verified',
                         size=len(data), sha256=checksum)
        except (BotoCoreError, ClientError, OSError, ValueError, KeyError) as error:
            reason = str(error) if isinstance(error, ValueError) else 'storage_failure'
            if reason not in ('size_mismatch', 'checksum_mismatch', 'destination_conflict'):
                reason = 'storage_failure'
            entry.update(status='failed', reason=reason)
            report.append(entry)
            raise CutoverStopped(report) from None
        report.append(entry)
    return report
