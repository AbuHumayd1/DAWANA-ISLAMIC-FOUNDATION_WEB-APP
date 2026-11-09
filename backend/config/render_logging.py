"""Useful server-error locations without exception messages, source or locals."""
from pathlib import Path
import re

from .staging_logging import RequestPrivacyFilter


def safe_name(value):
    return re.sub(r'[^a-zA-Z0-9_.<>-]', '_', value)[:100]


class RenderRequestPrivacyFilter(RequestPrivacyFilter):
    def filter(self, record):
        exception_info = record.exc_info
        super().filter(record)
        if exception_info:
            exception_type, _, traceback = exception_info
            locations = []
            while traceback is not None:
                code = traceback.tb_frame.f_code
                locations.append('%s:%s:%s' % (
                    safe_name(Path(code.co_filename).name), traceback.tb_lineno, safe_name(code.co_name)))
                traceback = traceback.tb_next
            record.msg = 'HTTP request failed (status=%s, exception=%s, locations=%s).'
            record.args = (getattr(record, 'status_code', 'unavailable'),
                safe_name(exception_type.__name__), ' > '.join(locations[-8:]))
        return True
