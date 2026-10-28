"""Additive launch schema. No data import, grants or publication."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion as deletion


def fk(to): return models.ForeignKey(to=to,on_delete=deletion.PROTECT)
def actor(): return models.ForeignKey(to=settings.AUTH_USER_MODEL,on_delete=deletion.SET_NULL,null=True,blank=True,related_name='+')
def auto(): return ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID'))
def updated(): return ('updated_at',models.DateTimeField(auto_now=True))
def created(): return ('created_at',models.DateTimeField(auto_now_add=True))


class Migration(migrations.Migration):
    dependencies=[('dic','0032_phase4_timetables'),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name='AcademicClass',fields=[auto(),('edition',fk('dic.campedition')),
            ('name',models.CharField(max_length=120)),('active',models.BooleanField(default=True)),('modified_by',actor()),updated()],
            options={'permissions':[('manage_dic_classes','Manage approved academic classes and assignments')],
                'constraints':[models.UniqueConstraint(fields=['edition','name'],name='dic_academic_name_unique')]}),
        migrations.CreateModel(name='AcademicAssignment',fields=[auto(),('edition',fk('dic.campedition')),
            ('participant',fk('dic.participant')),('academic_class',fk('dic.academicclass')),('modified_by',actor()),updated()],
            options={'constraints':[models.UniqueConstraint(fields=['edition','participant'],name='dic_academic_person_unique')]}),
        migrations.CreateModel(name='CampAnnouncement',fields=[auto(),('edition',fk('dic.campedition')),
            ('title',models.CharField(max_length=160)),('body',models.TextField(max_length=5000)),
            ('status',models.CharField(max_length=12,choices=[('draft','Draft'),('published','Published')],default='draft')),
            ('starts_at',models.DateTimeField(null=True,blank=True)),('ends_at',models.DateTimeField(null=True,blank=True)),
            ('modified_by',actor()),('published_by',actor()),created(),updated()],
            options={'ordering':['-created_at','-pk'],
                'permissions':[('manage_dic_announcements','Edit draft camp announcements'),('publish_dic_announcements','Publish and unpublish camp announcements')],
                'constraints':[models.CheckConstraint(condition=models.Q(starts_at__isnull=True)|models.Q(ends_at__isnull=True)|models.Q(ends_at__gt=models.F('starts_at')),name='dic_announcement_window'),
                    models.CheckConstraint(condition=models.Q(status__in=['draft','published']),name='dic_announcement_status')]}),
        migrations.CreateModel(name='ContactEnquiry',fields=[('id',models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,serialize=False)),
            ('name',models.CharField(max_length=120)),('email',models.EmailField(max_length=254)),('subject',models.CharField(max_length=200)),
            ('message',models.TextField(max_length=5000)),('status',models.CharField(max_length=12,choices=[('new','New'),('reviewing','Reviewing'),('closed','Closed')],default='new')),
            created(),updated()],options={'ordering':['-created_at']}),
        migrations.CreateModel(name='FoundationDonation',fields=[('id',models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,serialize=False)),
            ('request_id',models.UUIDField(unique=True)),('fingerprint',models.CharField(max_length=64,editable=False)),
            ('reference',models.CharField(max_length=100,unique=True,editable=False)),('token_digest',models.CharField(max_length=64,editable=False)),
            ('email',models.EmailField(max_length=254)),('amount_kobo',models.PositiveBigIntegerField()),('currency',models.CharField(max_length=3,default='NGN')),
            ('status',models.CharField(max_length=20,choices=[(s,s.replace('_',' ').title()) for s in ('created','initializing','pending','successful','failed','abandoned','review')],default='created')),
            ('authorization_url',models.URLField(blank=True)),('audit',models.JSONField(default=list,editable=False)),created(),updated()],
            options={'permissions':[('view_foundation_donations','View foundation donation reconciliation')],
                'constraints':[models.CheckConstraint(condition=models.Q(amount_kobo__gt=0,currency='NGN'),name='foundation_donation_money'),
                    models.CheckConstraint(condition=models.Q(status__in=['created','initializing','pending','successful','failed','abandoned','review']),name='foundation_donation_status')]}),
    ]
