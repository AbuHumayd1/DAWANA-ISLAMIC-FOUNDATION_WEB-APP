import uuid
from django.db import models
from django.db.models import Q


class ContactEnquiry(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    name=models.CharField(max_length=120)
    email=models.EmailField()
    subject=models.CharField(max_length=200)
    message=models.TextField(max_length=5000)
    status=models.CharField(max_length=12,choices=[('new','New'),('reviewing','Reviewing'),('closed','Closed')],default='new')
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    class Meta:
        ordering=['-created_at']


class FoundationDonation(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    request_id=models.UUIDField(unique=True)
    fingerprint=models.CharField(max_length=64,editable=False)
    reference=models.CharField(max_length=100,unique=True,editable=False)
    provider_mode=models.CharField(max_length=4,choices=[('test','Test'),('live','Live')],default='test',editable=False)
    token_digest=models.CharField(max_length=64,editable=False)
    email=models.EmailField()
    amount_kobo=models.PositiveBigIntegerField()
    currency=models.CharField(max_length=3,default='NGN')
    status=models.CharField(max_length=20,choices=[(s,s.replace('_',' ').title()) for s in ('created','initializing','pending','successful','failed','abandoned','review')],default='created')
    authorization_url=models.URLField(blank=True)
    audit=models.JSONField(default=list,editable=False)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    class Meta:
        permissions=[('view_foundation_donations','View foundation donation reconciliation')]
        constraints=[models.CheckConstraint(condition=Q(amount_kobo__gt=0,currency='NGN'),name='foundation_donation_money'),
            models.CheckConstraint(condition=Q(status__in=['created','initializing','pending','successful','failed','abandoned','review']),name='foundation_donation_status')]
