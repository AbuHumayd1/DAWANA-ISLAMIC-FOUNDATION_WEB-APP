import logging


class RequestPrivacyFilter(logging.Filter):
    def filter(self, record):
        record.msg = 'HTTP request rejected or failed (status=%s).'
        record.args = (getattr(record, 'status_code', 'unavailable'),)
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True
