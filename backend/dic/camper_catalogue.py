"""Read-only public fields of the existing fixed approved scoring policy.

This is a catalogue, not scheduled/published tasks or a participation workflow.
Calling this function never determines completion or awards any points.
"""
from .scoring_catalogue import catalogue_options


def camper_catalogue(edition_year, storage_ready):
    if edition_year != 2026 or not storage_ready:
        return dict(ready=False, activities=[], message='The approved points catalogue is not available for this camp yet.')
    policy = catalogue_options()
    if not policy['ready']:
        return dict(ready=False, activities=[], message='The approved points catalogue is awaiting review.')
    fields = ('code', 'name', 'kind', 'category', 'points', 'frequency', 'mode', 'threshold')
    # Do not return staff member lists, award evidence, private participation or
    # invented availability/completion/deadline/publication states.
    return dict(ready=True, activities=[{key: row[key] for key in fields}
        for kind in ('individual', 'collective') for row in policy[kind]],
        message='Fixed approved DIC 2026 scoring activities. An authorized officer verifies and records awards.')
