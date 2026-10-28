"""Production renderer adapter checks; SimpleTestCase forbids database access."""
import base64
import io
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from .portrait_pdf import render_pdf
from .premium_hybrid_badge import render_hybrid_pdf, QR


class HybridPortraitIntegrationTests(SimpleTestCase):
    def card(self):
        return dict(enrollment=SimpleNamespace(participant=SimpleNamespace(full_name='Participant Example'),
            edition=SimpleNamespace(name='Darul Islam Camp 2026'),participant_number='DIC-2026-EXAMPLE'),
            portrait=None,portrait_status='Photograph pending',
            verification_url='https://example.invalid/dic/ids/verify/#EXISTING-SYNTHETIC-TEST-PAYLOAD')

    def test_production_uses_exact_approved_hybrid_and_server_resolved_house(self):
        import fitz
        card = {**self.card(),'synthetic':True,'house':'Untrusted override','house_colour':'#ffffff'}
        approved = {**card,'house':'Configured test house','house_colour':'#123456','house_assigned':True}
        with patch('dic.portrait_pdf.house_details',return_value=('Configured test house','#123456')) as lookup:
            actual = fitz.open(stream=render_pdf([card]),filetype='pdf')
        expected = fitz.open(stream=render_hybrid_pdf([approved]),filetype='pdf')
        self.assertEqual(actual[0].get_pixmap().samples,expected[0].get_pixmap().samples)
        lookup.assert_called_once_with(card['enrollment'])
        self.assertNotIn('Untrusted override',actual[0].get_text())

    def test_production_has_no_preview_label_and_reuses_verbatim_qr_without_issuance(self):
        import cv2
        import fitz
        import numpy as np
        card = self.card()
        original_url = card['verification_url']
        with patch('dic.portrait_pdf.house_details',return_value=('Housing assignment pending',None)):
            pdf = fitz.open(stream=render_pdf([card]),filetype='pdf')
        text = pdf[0].get_text()
        self.assertNotIn('SYNTHETIC CONCEPT',text)
        self.assertNotIn('NOT A VALID ID',text)
        self.assertIn('Housing assignment pending',text)
        self.assertIn(card['enrollment'].participant_number,text)
        from .portrait_pdf import mm
        x,t,size = QR
        image = pdf[0].get_pixmap(matrix=fitz.Matrix(6,6),clip=fitz.Rect((12+x)*mm,(15.5+t)*mm,(12+x+size)*mm,(15.5+t+size)*mm))
        rgb = np.frombuffer(image.samples,dtype=np.uint8).reshape(image.height,image.width,image.n)
        decoded,_,_ = cv2.QRCodeDetector().detectAndDecode(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        self.assertEqual(decoded,original_url)
        self.assertEqual(card['verification_url'],original_url)
        # SimpleTestCase makes any unintended ORM/issuance activity an error.

    def test_production_retains_photo_and_165_character_name(self):
        import fitz
        from PIL import Image
        buffer = io.BytesIO()
        Image.new('RGB',(120,180),'#abc123').save(buffer,format='PNG')
        card = self.card()
        card['enrollment'].participant.full_name = 'SYNTHETIC '+('Abdulrahman Olayiwola Muhammad '*5)
        card['portrait'] = 'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()
        with patch('dic.portrait_pdf.house_details',return_value=('Assigned test house',None)):
            pdf = fitz.open(stream=render_pdf([card]),filetype='pdf')
        self.assertIn(''.join(card['enrollment'].participant.full_name.split()),''.join(pdf[0].get_text().split()))
        photos = [image for image in pdf[0].get_image_info() if image['width']==120 and image['height']==180]
        self.assertEqual(len(photos),1)
        bounds = fitz.Rect(photos[0]['bbox'])
        self.assertAlmostEqual(bounds.width/bounds.height,120/180,places=4)
