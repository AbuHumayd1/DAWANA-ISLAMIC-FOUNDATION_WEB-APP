"""Preview-only regression tests. SimpleTestCase forbids database access."""
import hashlib
import base64
import io
from types import SimpleNamespace
from django.test import SimpleTestCase
from .premium_hybrid_badge import render_hybrid_pdf,plan_name,NAME_BOX,MIN_NAME_PT,QR
from .premium_badge_concepts import render_concept_pdf,CONCEPTS,NEUTRAL
from .portrait_pdf import mm


class PremiumHybridBadgeTests(SimpleTestCase):
    def card(self,index=1,name='SYNTHETIC Participant 01',colour='#123456'):
        return dict(synthetic=True,enrollment=SimpleNamespace(edition=SimpleNamespace(name='Darul Islam Camp 2026'),
            participant=SimpleNamespace(full_name=name),participant_number=f'SYNTHETIC-{index:04d}'),
            portrait=None,portrait_status='Photograph pending',house='SYNTHETIC HOUSE A' if colour else 'Housing assignment pending',
            house_colour=colour,house_assigned=bool(colour),verification_url=f'https://example.invalid/dic/ids/verify/#SYNTHETIC-{index:04d}')

    def test_ordinary_name_fits_one_readable_line_and_wrapped_names_avoid_number_orphan(self):
        fitted = plan_name('SYNTHETIC Participant 01')
        self.assertEqual(fitted.lines,('SYNTHETIC Participant 01',))
        self.assertGreaterEqual(fitted.font_size,16)
        fitted = plan_name('SYNTHETIC Participant ExtraordinarilyLongSurname 01')
        self.assertGreater(len(fitted.lines),1)
        self.assertNotEqual(fitted.lines[-1].strip(),'01')

    def test_name_preservation_readability_actual_bounds_and_neighbour_separation(self):
        import fitz
        names = ['SYNTHETIC Ali','SYNTHETIC Participant 01',
            'SYNTHETIC '+('Abdulrahman Olayiwola Muhammad '*5),
            'SYNTHETIC '+('AbdulrahmanOlayiwolaMuhammadAbdulazeezAdebayo'*2)+' Participant']
        for name in names:
            with self.subTest(name=name):
                card = self.card(name=name)
                placements = []
                pdf = fitz.open(stream=render_hybrid_pdf([card],placements=placements),filetype='pdf')
                record = placements[0]
                x,t,w,h = NAME_BOX
                bounds = fitz.Rect((12+x)*mm,(15.5+t)*mm,(12+x+w)*mm,(15.5+t+h)*mm)
                spans = [s for block in pdf[0].get_text('dict')['blocks'] if 'lines' in block
                    for line in block['lines'] for s in line['spans']
                    if s['size']>=MIN_NAME_PT-.01 and bounds.intersects(fitz.Rect(s['bbox']))]
                self.assertTrue(spans)
                self.assertEqual(''.join(name.split()),''.join(''.join(s['text'] for s in spans).split()))
                for span in spans:
                    x0,y0,x1,y1 = span['bbox']
                    self.assertGreaterEqual(x0,bounds.x0-.05)
                    self.assertGreaterEqual(y0,bounds.y0-.05)
                    self.assertLessEqual(x1,bounds.x1+.05)
                    self.assertLessEqual(y1,bounds.y1+.05)
                    self.assertLess(y1,(15.5+record['label_top'])*mm)
                self.assertGreaterEqual(record['name_size'],MIN_NAME_PT)
                self.assertGreaterEqual(record['name_top'],QR[1]+QR[2]+6)
                self.assertLess(record['number_top']+5,record['house_top'])
                self.assertGreaterEqual(record['house_height'],9)
                self.assertLessEqual(record['house_height'],12)
                self.assertLessEqual(record['house_top']+record['house_height'],124.001)

    def test_exact_geometry_pagination_and_cutting_guides(self):
        import fitz
        for count,pages in [(1,1),(4,1),(17,5)]:
            pdf = fitz.open(stream=render_hybrid_pdf([self.card(i+1) for i in range(count)]),filetype='pdf')
            self.assertEqual(len(pdf),pages)
            for index,page in enumerate(pdf):
                self.assertAlmostEqual(page.rect.width/mm,210,places=3)
                self.assertAlmostEqual(page.rect.height/mm,297,places=3)
                self.assertEqual(page.rotation,0)
                drawings = page.get_drawings()
                rectangles = [d['rect'] for d in drawings if abs(d['rect'].width-90*mm)<.01 and abs(d['rect'].height-130*mm)<.01]
                expected = min(4,count-index*4)
                self.assertEqual(len(rectangles),expected)
                for slot,rect in enumerate(rectangles):
                    self.assertAlmostEqual(rect.x0/mm,12+slot%2*96,places=3)
                    self.assertAlmostEqual(rect.y0/mm,15.5+slot//2*136,places=3)
                lines = [d for d in drawings if d['type']=='s' and len(d['items'])==1 and d['items'][0][0]=='l']
                self.assertEqual(len(lines),expected*8)

    def test_configured_house_and_neutral_pending_ribbons_keep_green_edge_and_placeholder(self):
        import fitz
        for colour in ('#123456',None):
            card = self.card(colour=colour)
            positions = []
            pdf = fitz.open(stream=render_hybrid_pdf([card],placements=positions),filetype='pdf')
            top = positions[0]['house_top']+positions[0]['house_height']/2
            def sample(x,y):
                return pdf[0].get_pixmap(matrix=fitz.Matrix(3,3),clip=fitz.Rect((12+x)*mm,(15.5+y)*mm,(12+x+.4)*mm,(15.5+y+.4)*mm)).samples[:3]
            self.assertTrue(all(abs(a-b)<=2 for a,b in zip(sample(9.5,top),bytes.fromhex((colour or NEUTRAL)[1:]))))
            self.assertTrue(all(abs(a-b)<=2 for a,b in zip(sample(1.5,top),(23,74,52))))
            self.assertIn(card['house'],pdf[0].get_text())
            self.assertIn('Photograph pending',pdf[0].get_text())

    def test_qr_payload_remains_readable(self):
        import cv2
        import fitz
        import numpy as np
        card = self.card()
        pdf = fitz.open(stream=render_hybrid_pdf([card]),filetype='pdf')
        x,t,size = QR
        image = pdf[0].get_pixmap(matrix=fitz.Matrix(6,6),clip=fitz.Rect((12+x)*mm,(15.5+t)*mm,(12+x+size)*mm,(15.5+t+size)*mm))
        rgb = np.frombuffer(image.samples,dtype=np.uint8).reshape(image.height,image.width,image.n)
        actual,_,_ = cv2.QRCodeDetector().detectAndDecode(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        self.assertEqual(actual,card['verification_url'])

    def test_supplied_photograph_is_embedded_without_aspect_ratio_distortion(self):
        import fitz
        from PIL import Image
        image = io.BytesIO()
        Image.new('RGB',(120,180),'#ab8765').save(image,format='PNG')
        card = self.card()
        card['portrait'] = 'data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()
        pdf = fitz.open(stream=render_hybrid_pdf([card]),filetype='pdf')
        portraits = [entry for entry in pdf[0].get_image_info() if entry['width']==120 and entry['height']==180]
        self.assertEqual(len(portraits),1)
        bounds = fitz.Rect(portraits[0]['bbox'])
        self.assertAlmostEqual(bounds.width/bounds.height,120/180,places=4)
        self.assertGreaterEqual(bounds.x0,(12+9)*mm-.01)
        self.assertGreaterEqual(bounds.y0,(15.5+36)*mm-.01)
        self.assertLessEqual(bounds.x1,(12+41)*mm+.01)
        self.assertLessEqual(bounds.y1,(15.5+73)*mm+.01)

    def test_old_concepts_render_identically_before_and_after_hybrid_and_real_contexts_are_rejected(self):
        import fitz
        card = self.card()
        def pixels(concept):
            pdf = fitz.open(stream=render_concept_pdf([card],concept),filetype='pdf')
            return hashlib.sha256(pdf[0].get_pixmap().samples).hexdigest()
        before = {key:pixels(key) for key in CONCEPTS}
        render_hybrid_pdf([card])
        self.assertEqual(before,{key:pixels(key) for key in CONCEPTS})
        self.assertEqual(tuple(CONCEPTS),('classic-executive','modern-premium'))
        with self.assertRaises(ValueError):
            render_hybrid_pdf([{**card,'synthetic':False}])
