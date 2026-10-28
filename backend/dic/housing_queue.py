"""PostgreSQL durable queue. No signals, payment hooks or external broker."""
import uuid
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .allocation import AllocationError, unallocated_paid_participants
from .housing_service import audit, permitted, allocate_batch, members_for, set_group_jobs
from .models import CampEdition, HousingJob

LEASE = timedelta(minutes=15)


@transaction.atomic
def discover(edition_id, actor, limit=100):
    permitted(actor, 'can_process_housing_queue')
    edition = CampEdition.objects.select_for_update().get(pk=edition_id)
    created = 0
    # Select candidates without a job before LIMIT; held jobs do not starve discovery.
    known = HousingJob.objects.filter(edition=edition).values_list('participant_id', flat=True)
    for participant in unallocated_paid_participants(edition).exclude(pk__in=known)[:limit]:
        job, new = HousingJob.objects.get_or_create(edition=edition, participant=participant)
        if new:
            created += 1
            audit(actor, 'housing_job_discovered', job, {'state': 'pending'})
    return created


@transaction.atomic
def claim(edition_id, actor):
    permitted(actor, 'can_process_housing_queue')
    expired = timezone.now() - LEASE
    job = (HousingJob.objects.select_for_update(skip_locked=True).filter(edition_id=edition_id)
           .filter(Q(state='pending') | Q(state='processing', claimed_at__lt=expired))
           .order_by('created_at', 'pk').first())
    if not job:
        return None
    before = job.state
    if before == 'processing' and job.attempts >= 3:
        job.state, job.reason, job.claimed_at = 'failed', 'Interrupted repeatedly; explicit supervisor retry required.', None
    else:
        job.state, job.claimed_at, job.claim_token = 'processing', timezone.now(), uuid.uuid4()
        job.attempts += 1
        job.reason = 'Recovered expired claim.' if before == 'processing' else ''
    job.save()
    audit(actor, 'housing_job_claimed' if job.state == 'processing' else 'housing_job_failed', job,
          {'before': before, 'after': job.state, 'attempt': job.attempts, 'reason': job.reason})
    return job.pk, job.claim_token


@transaction.atomic
def process_claim(job_id, token, actor):
    permitted(actor, 'can_process_housing_queue')
    permitted(actor, 'can_allocate_participants')
    edition_id = HousingJob.objects.values_list('edition_id', flat=True).get(pk=job_id)
    CampEdition.objects.select_for_update().get(pk=edition_id)
    job = HousingJob.objects.select_for_update().get(pk=job_id)
    if job.state != 'processing' or job.claim_token != token:
        return job.state  # Another group completed this job, or an expired claim was recovered.
    try:
        # Savepoint rolls back ALL group allocations and their audits on any failure.
        with transaction.atomic():
            allocate_batch(edition_id, [job.participant_id], actor)
        job.refresh_from_db()
        if job.state != 'completed':
            job.state, job.reason = 'completed', 'Verified allocation complete.'
    except (AllocationError, ValidationError) as exc:
        job.state, job.reason = 'held', '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
    except Exception as exc:
        # Do not persist connection strings or other exception payloads.
        job.state, job.reason = 'failed', f'{type(exc).__name__}: processing failed; inspect locally and explicitly retry.'
    if job.state in ('held', 'failed'):
        members = members_for(job.participant, job.edition, strict=False)
        set_group_jobs(job.edition, members, job.state, job.reason, actor)
    job.claimed_at = None
    job.save()
    audit(actor, 'housing_job_' + job.state, job,
          {'before': 'processing', 'after': job.state, 'reason': job.reason, 'attempt': job.attempts})
    return job.state


@transaction.atomic
def retry(job_id, actor, reason):
    permitted(actor, 'can_process_housing_queue')
    if not reason.strip():
        raise AllocationError('An explicit retry reason is required.')
    edition_id = HousingJob.objects.values_list('edition_id', flat=True).get(pk=job_id)
    CampEdition.objects.select_for_update().get(pk=edition_id)
    job = HousingJob.objects.select_for_update().get(pk=job_id)
    if job.state not in ('held', 'failed'):
        raise AllocationError('Only held or failed jobs can be retried.')
    before = job.state
    job.state, job.reason, job.claimed_at = 'pending', reason, None
    job.claim_token = uuid.uuid4()
    job.save()
    audit(actor, 'housing_job_retried', job, {'before': before, 'after': 'pending', 'reason': reason})

