"""Additive release controls and retained certificate records; no automatic issuance."""
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from .recording_storage import recording_storage, validate_recording


class LectureRecording(models.Model):
    edition=models.ForeignKey('dic.CampEdition',on_delete=models.PROTECT)
    session=models.ForeignKey('dic.TimetableEntry',on_delete=models.SET_NULL,null=True,blank=True)
    title=models.CharField(max_length=200)
    lecturer=models.CharField(max_length=200,blank=True)
    description=models.TextField(blank=True,max_length=5000)
    audio=models.FileField(storage=recording_storage,validators=[validate_recording],max_length=200)
    state=models.CharField(max_length=12,choices=[('draft','Draft'),('published','Published')],default='draft')
    published_at=models.DateTimeField(null=True,editable=False)
    published_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL,editable=False,related_name='+')
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=['-updated_at','-pk']
        permissions=[('publish_lecturerecording','Publish or withdraw lecture recordings')]
    def clean(self):
        if self.session_id and self.session.edition_id != self.edition_id:
            raise ValidationError('Programme session and recording must belong to the same edition.')
    def save(self,*args,actor=None,**kwargs):
        self.clean()
        if self.state=='published':
            if not actor or not actor.is_active or not actor.is_staff or not actor.has_perm('dic.publish_lecturerecording'):
                raise ValidationError('Explicit media publication authority is required.')
            self.published_by=actor; self.published_at=timezone.now()
        else: self.published_at=None; self.published_by=None
        super().save(*args,**kwargs)
    def __str__(self): return self.title


class CertificateRelease(models.Model):
    edition=models.OneToOneField('dic.CampEdition',on_delete=models.PROTECT)
    enabled=models.BooleanField(default=False)
    release_at=models.DateTimeField(null=True,blank=True,help_text='Exact owner-approved release hour, Africa/Lagos; blank blocks release.')
    artwork=models.CharField(max_length=200,default='dic_2026_certificate.png')
    artwork_sha256=models.CharField(max_length=64,blank=True)
    name_box=models.JSONField(default=list,blank=True,help_text='Approved [x,y,width,height] in PDF points, origin bottom-left; required before release.')
    reference_box=models.JSONField(default=list,blank=True,help_text='Optional approved [x,y,width,height] for reference text.')
    page_width=models.PositiveIntegerField(default=842)
    page_height=models.PositiveIntegerField(default=595)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        permissions=[('release_dic_certificates','Configure and release participant certificates')]
    def clean(self):
        from pathlib import PurePosixPath
        path=PurePosixPath(self.artwork)
        if path.is_absolute() or ':' in self.artwork or chr(0) in self.artwork or '..' in path.parts or chr(92) in self.artwork:
            raise ValidationError('Use a relative approved artwork path.')
        if path.suffix.lower() not in ('.png','.jpg','.jpeg'):
            raise ValidationError('Use the approved PNG or JPEG designer export.')
        if self.release_at and timezone.localtime(self.release_at).date() < self.edition.camp_end_date:
            raise ValidationError('Certificates may not be released before the final camp day.')
        for box in (self.name_box,self.reference_box):
            if box and (not isinstance(box,list) or len(box)!=4 or any(type(v) not in (int,float) for v in box)
                or box[0]<0 or box[1]<0 or box[2]<=0 or box[3]<=0 or box[0]+box[2]>self.page_width or box[1]+box[3]>self.page_height):
                raise ValidationError('Certificate text boxes must fit within the approved artwork.')
        if self.enabled and (not self.release_at or not self.artwork_sha256 or not self.name_box or not self.reference_box):
            raise ValidationError('Approve artwork, name/reference placement and an exact release time before enabling certificates.')
    def save(self,*args,**kwargs):
        self.full_clean();super().save(*args,**kwargs)
    def __str__(self): return str(self.edition)


class ParticipationCertificate(models.Model):
    reference=models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
    edition=models.ForeignKey('dic.CampEdition',on_delete=models.PROTECT)
    participant=models.ForeignKey('dic.Participant',on_delete=models.PROTECT)
    participant_name=models.CharField(max_length=200)
    revision=models.PositiveIntegerField(default=1)
    issued_at=models.DateTimeField(auto_now_add=True)
    revoked_at=models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['edition','participant'],name='dic_certificate_person_unique')]
        permissions=[('manage_dic_certificates','Revoke or reissue participation certificates')]
    def __str__(self): return str(self.reference)
