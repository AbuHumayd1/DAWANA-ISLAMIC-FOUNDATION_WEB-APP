"""Committee-authored observations, kept separate from automated camp evidence."""
from django.conf import settings
from django.db import models
from django.utils import timezone

ASSESSMENT_TOPICS = [
    ('programme', 'Programme delivery'),
    ('teaching', 'Teaching and Qur’an learning'),
    ('catering', 'Catering and food service'),
    ('competitions', 'Competitions and house championships'),
    ('operations', 'Camp operations and logistics'),
    ('achievements', 'Achievements and positive outcomes'),
    ('challenges', 'Challenges and lessons learned'),
    ('recommendations', 'Recommendations for the next edition'),
]


class AftercampAssessment(models.Model):
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT, related_name='aftercamp_assessments')
    topic = models.CharField(max_length=20, choices=ASSESSMENT_TOPICS)
    findings = models.TextField(blank=True, max_length=10000)
    challenges = models.TextField(blank=True, max_length=6000)
    recommendations = models.TextField(blank=True, max_length=6000)
    evidence_reference = models.TextField(blank=True, max_length=1500)
    status = models.CharField(max_length=12, choices=[('draft', 'Draft'), ('approved', 'Approved')], default='draft')
    authored_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['edition', 'topic'], name='dic_aftercamp_topic_edition_unique')]
        ordering = ['topic']

    def __str__(self):
        return f'{self.edition_id} · {self.topic} ({self.status})'
