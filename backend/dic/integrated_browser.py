"""Explicit browser acceptance with real Django sessions and synthetic records."""
import os,json,subprocess,sys
from pathlib import Path
from datetime import date,datetime,timezone as utc
from unittest import skipUnless
from unittest.mock import patch
from django.test import LiveServerTestCase,override_settings
from django.contrib.auth import get_user_model
from .test_participant_portal import PortalFixtures,TEST_DELIVERY
from .models import TimetableEntry,LectureRecording
from .management.commands.initialize_dic2026_release import initialize
from .timetable_services import publish_days

@skipUnless(os.environ.get('DIC_INTEGRATED_BROWSER')=='1','Explicit local browser acceptance')
@override_settings(**TEST_DELIVERY,CSRF_TRUSTED_ORIGINS=['http://127.0.0.1:5186'])
class IntegratedBrowserTests(PortalFixtures,LiveServerTestCase):
    host='127.0.0.1'
    def setUp(self):
        self.clock=patch('django.utils.timezone.now',return_value=datetime(2026,12,28,10,tzinfo=utc.utc));self.clock.start();self.addCleanup(self.clock.stop)
        PortalFixtures.setUp(self)
        self.edition.year=2026;self.edition.camp_start_date=date(2026,12,23);self.edition.camp_end_date=date(2027,1,1)
        self.edition.save(update_fields=['year','camp_start_date','camp_end_date'])
        self.owner=get_user_model().objects.create_superuser('browser-owner','owner@example.test','synthetic')
        items=list(self.paid_order.items.select_related('participant').order_by('pk'))
        items[0].participant.full_name='Brother Browser';items[0].participant.save()
        items[1].participant.full_name='Sister Browser';items[1].participant.sex='Female';items[1].participant.save()
        initialize(self.edition,self.owner)
        for kind in ('activities','food'):publish_days(self.owner,TimetableEntry.objects.filter(edition=self.edition,timetable_type=kind),True)
        row=LectureRecording.objects.create(edition=self.edition,title='Approved Browser Lecture',lecturer='Approved Lecturer',audio='camp-recordings/test.mp3')
        row.state='published';row.save(actor=self.owner)
    def test_real_camper_context_programme_media_and_mobile_layout(self):
        client,_=self.login()
        env={**os.environ,'CAMP_FOREIGN_ITEM':str(self.unpaid_order.items.first().pk),'CAMP_TEST_API':self.live_server_url,'CAMP_TEST_COOKIE':'; '.join(key+'='+value.value for key,value in client.cookies.items())}
        result=subprocess.run(['node','scripts/check-integrated-camp.cjs'],cwd=Path(__file__).resolve().parents[2]/'dawana-platform',env=env,stdout=sys.stdout,stderr=sys.stderr,text=True,timeout=240)
        self.assertEqual(result.returncode,0)
