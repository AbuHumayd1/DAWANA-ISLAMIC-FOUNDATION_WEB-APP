"""Worker heartbeat in the existing shared database cache; no new data service."""
from time import time
from django.core.cache import cache

KEY = 'dic-native-worker-heartbeat'


def beat():
    cache.set(KEY, time(), timeout=600)


def healthy():
    stamp = cache.get(KEY)
    return type(stamp) in (int, float) and 0 <= time() - stamp <= 300
