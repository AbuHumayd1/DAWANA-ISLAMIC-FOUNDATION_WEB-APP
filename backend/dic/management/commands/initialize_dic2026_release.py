"""Explicit additive reference initialization; never runs at startup."""
import hashlib,json,unicodedata,re
from pathlib import Path
from datetime import date,time
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth import get_user_model
from django.db import connection,transaction
from dic.models import CampEdition,TimetableEntry,House,DICAdminAuditEvent,CertificateRelease,AcademicClass
SOURCE=Path(__file__).resolve().parents[2]/'data/dic2026_approved_release.json'
NAMES=[('abdullah','‘Abdullāh ibn Umm Maktūm','male'),('bara','Al-Barā’ ibn Mālik','male'),('ukkashah','‘Ukkāshah ibn Miḥṣan','male'),('usayd','Usayd ibn Huḍayr','male'),('shifa','Al-Shifā’ bint ‘Abdullāh','female'),('asma','Asmā’ bint Yazīd','female'),('nusaybah','Nusaybah bint Ka‘b','female'),('sulaym','Umm Sulaym','female')]
def canonical(value):
    return re.sub('[^a-z]','',unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower())
@transaction.atomic
def initialize(edition,actor):
    edition=CampEdition.objects.select_for_update().get(pk=edition.pk)
    if edition.year!=2026 or edition.camp_start_date!=date(2026,12,23) or edition.camp_end_date!=date(2027,1,1):raise CommandError('Exact approved camp dates are required.')
    receipt=dict(action='dic2026_integrated_reference_initialized',target_type='CampEdition',target_id=str(edition.pk))
    if DICAdminAuditEvent.objects.filter(**receipt).exists():return 0
    source=json.loads(SOURCE.read_text(encoding='utf-8'));count=0
    for value in source['entries']:
        row=dict(value);row['date']=date.fromisoformat(row['date'])
        for key in ('start_time','end_time'):row[key]=time.fromisoformat(row[key]) if row[key] else None
        if TimetableEntry.objects.filter(edition=edition,source_key=row['source_key']).exists():continue
        # Existing manually entered schedules win; never seed overlapping replacements silently.
        if TimetableEntry.objects.filter(edition=edition,date=row['date'],timetable_type=row['timetable_type']).exclude(source_key__startswith='dic2026:').exists():continue
        TimetableEntry.objects.create(edition=edition,modified_by=actor,**row);count+=1
    known={canonical(name) for _,name,_ in NAMES}
    if any(not h.canonical_key and canonical(h.name) not in known for h in House.objects.filter(edition=edition,purpose='participants')):
        raise CommandError('Existing unmatched house names need canonical reconciliation in Admin; no reference data was changed.')
    for key,name,gender in NAMES:
        if House.objects.filter(edition=edition,canonical_key=key).exists():continue
        matches=[h for h in House.objects.filter(edition=edition,gender=gender) if canonical(h.name)==canonical(name)]
        if len(matches)>1:raise CommandError('Ambiguous canonical house; review before initialization.')
        if matches:
            House.objects.filter(pk=matches[0].pk).update(canonical_key=key)
        else:House.objects.create(edition=edition,canonical_key=key,name=name,gender=gender,capacity=None)
    for name in ("Ta'lim",'Tahdheeb',"Da'wah"):
        AcademicClass.objects.get_or_create(edition=edition,name=name,defaults={'modified_by':actor})
    CertificateRelease.objects.get_or_create(edition=edition)
    DICAdminAuditEvent.objects.create(actor=actor,**receipt,details={'entries':count,'sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest()})
    return count
class Command(BaseCommand):
    help='Preview approved reference content; --apply requires exact database, source checksum and named authorized actor. Imports drafts only.'
    def add_arguments(self,p):
        p.add_argument('--edition',type=int,required=True);p.add_argument('--apply',action='store_true');p.add_argument('--database-name');p.add_argument('--approved-by');p.add_argument('--source-sha256')
    def handle(self,*args,**o):
        digest=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        if not o['apply']:self.stdout.write('PREVIEW ONLY: approved programme, 27 specified meals, eight houses with unset capacities. SHA256 '+digest);return
        if o['database_name']!=connection.settings_dict['NAME'] or o['source_sha256']!=digest or not o['approved_by']:raise CommandError('Exact database, reviewed source hash and authorized actor required.')
        actor=get_user_model().objects.get(username=o['approved_by'],is_active=True,is_staff=True)
        if not actor.has_perm('dic.manage_dic_timetables') or not actor.has_perm('dic.add_house'):raise CommandError('Timetable and house initialization permissions required.')
        self.stdout.write(str(initialize(CampEdition.objects.get(pk=o['edition']),actor))+' drafts added. Nothing published; existing edits retained.')
