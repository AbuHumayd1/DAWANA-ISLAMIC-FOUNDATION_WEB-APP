"""Approved edition-specific housing configuration; never seeds on import."""
import json
from pathlib import Path


def house_capacity_limit(edition):
    return 30 if edition.year == 2026 else 25


def approved_2026_houses():
    return json.loads((Path(__file__).parent / 'config' / 'dic_2026_houses.json').read_text(encoding='utf-8'))['houses']
