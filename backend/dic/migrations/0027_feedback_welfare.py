"""PROPOSED ONLY: schema/privacy review and explicit approval before application."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion as deletion
import django.utils.timezone


def fk(target, **kwargs):
    return models.ForeignKey(target,on_delete=deletion.PROTECT,**kwargs)


def auto_id():
    return ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID'))


class Migration(migrations.Migration):
    dependencies = [('dic','0026_house_score_transaction'),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='AnonymousCamperResponse',fields=[
            ('id',models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,serialize=False)),
            ('edition',fk('dic.campedition')),('day',models.DateField()),
            ('channel',models.CharField(max_length=8,choices=[('daily','Daily'),('final','Final')])),
            ('ratings',models.JSONField()),('answers',models.JSONField(default=dict)),
        ],options={'default_permissions':(),'permissions':[('can_view_dic_feedback','Can view DIC feedback summaries'),('can_read_dic_feedback_details','Can read feedback comments and identified responses')],
            'constraints':[models.CheckConstraint(condition=models.Q(channel__in=('daily','final')),name='dic_camper_feedback_channel')]}),
        migrations.CreateModel(name='CamperFeedbackReceipt',fields=[
            ('digest',models.CharField(primary_key=True,max_length=64,editable=False,serialize=False)),
        ],options={'default_permissions':()}),
        migrations.CreateModel(name='LecturerFeedbackAccess',fields=[auto_id(),
            ('edition',fk('dic.campedition')),('user',fk(settings.AUTH_USER_MODEL)),('lecturer',fk('dic.lecturer')),('enabled',models.BooleanField(default=True)),
        ],options={'default_permissions':(),'permissions':[('can_configure_dic_feedback','Can configure DIC lecturer feedback access')],
            'constraints':[models.UniqueConstraint(fields=('edition','user'),name='dic_lecturer_feedback_account'),models.UniqueConstraint(fields=('edition','lecturer'),name='dic_lecturer_feedback_identity')]}),
        migrations.CreateModel(name='IdentifiedFeedback',fields=[auto_id(),
            ('edition',fk('dic.campedition')),('author',fk(settings.AUTH_USER_MODEL)),('lecturer',fk('dic.lecturer',null=True,blank=True)),
            ('channel',models.CharField(max_length=8,choices=[('staff','Staff'),('lecturer','Lecturer')])),('day',models.DateField()),
            ('ratings',models.JSONField()),('answers',models.JSONField(default=dict)),('created_at',models.DateTimeField(default=django.utils.timezone.now,editable=False)),
        ],options={'default_permissions':(),'permissions':[('can_submit_dic_staff_feedback','Can submit identified DIC staff feedback'),('can_submit_dic_lecturer_feedback','Can submit identified DIC lecturer feedback')],
            'constraints':[models.UniqueConstraint(fields=('edition','author','channel','day'),name='dic_identified_feedback_once'),models.CheckConstraint(condition=models.Q(channel='staff',lecturer__isnull=True)|models.Q(channel='lecturer',lecturer__isnull=False),name='dic_feedback_identity_kind')]}),
        migrations.CreateModel(name='WelfareReport',fields=[
            ('id',models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,serialize=False)),('edition',fk('dic.campedition')),
            ('reporter_user',fk(settings.AUTH_USER_MODEL,null=True,blank=True,related_name='dic_welfare_reports')),('reporter_registrant',fk('dic.primaryregistrant',null=True,blank=True)),
            ('assistance_person',models.CharField(max_length=200,blank=True)),('category',models.CharField(max_length=16)),('description',models.TextField(max_length=5000)),
            ('status',models.CharField(max_length=8,default='new')),('assigned_to',fk(settings.AUTH_USER_MODEL,null=True,blank=True,related_name='dic_welfare_assignments')),
            ('created_at',models.DateTimeField(default=django.utils.timezone.now,editable=False)),('version',models.PositiveIntegerField(default=1)),('request_id',models.UUIDField(unique=True,editable=False)),
        ],options={'default_permissions':(),'permissions':[('can_submit_dic_welfare','Can submit identified DIC welfare reports'),('can_view_dic_welfare','Can access confidential DIC welfare reports'),('can_manage_dic_welfare','Can manage confidential DIC welfare reports')],
            'constraints':[models.CheckConstraint(condition=models.Q(reporter_user__isnull=False,reporter_registrant__isnull=True)|models.Q(reporter_user__isnull=True,reporter_registrant__isnull=False),name='dic_welfare_one_reporter'),models.CheckConstraint(condition=models.Q(status__in=('new','review','resolved','closed')),name='dic_welfare_valid_status'),models.CheckConstraint(condition=models.Q(category__in=('health','accommodation','safety','bullying','assistance','other')),name='dic_welfare_valid_category')]}),
        migrations.CreateModel(name='WelfareEvent',fields=[auto_id(),('report',fk('dic.welfarereport',related_name='events')),('actor',fk(settings.AUTH_USER_MODEL,null=True,blank=True)),
            ('kind',models.CharField(max_length=8)),('note',models.TextField(max_length=3000,blank=True)),('changes',models.JSONField(default=dict)),
            ('created_at',models.DateTimeField(default=django.utils.timezone.now,editable=False)),('request_id',models.UUIDField(default=uuid.uuid4,unique=True,editable=False)),
        ],options={'default_permissions':()}),
    ]
