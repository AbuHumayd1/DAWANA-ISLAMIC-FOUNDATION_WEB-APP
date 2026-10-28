"""Portrait design checks without database creation or access."""
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from .portrait_pdf import geometry, render_pdf, mm


class PortraitDesignTests(SimpleTestCase):
    def test_exact_portrait_dimensions_reject_landscape_or_scaled_configuration(self):
        self.assertEqual(geometry(), (90*mm, 130*mm, 6*mm))
        for dimensions in [(130, 90), (85.6, 54), (85, 130)]:
            with override_settings(DIC_ID_BADGE_SIZE_MM=dimensions), self.assertRaises(ValueError):
                geometry()

    def test_four_up_pdf_preserves_portrait_bounds_and_continuous_green_frame(self):
        import fitz
        cards = [dict(enrollment=SimpleNamespace(participant=SimpleNamespace(full_name='SYNTHETIC Long Participant Name'),
            participant_number=f'SYNTHETIC-{i}', edition=SimpleNamespace(name='Darul Islam Camp 2026')),
            portrait=None, portrait_status='Photograph pending', verification_url=f'https://example.invalid/synthetic/{i}') for i in range(5)]
        with patch('dic.portrait_pdf.house_details', return_value=('SYNTHETIC HOUSE', '#123456')):
            document = fitz.open(stream=render_pdf(cards), filetype='pdf')
        self.assertEqual(len(document), 2)
        for index, page in enumerate(document):
            rectangles = [d['rect'] for d in page.get_drawings() if abs(d['rect'].width-90*mm)<.01 and abs(d['rect'].height-130*mm)<.01]
            self.assertEqual(len(rectangles), 4 if index == 0 else 1)
            for slot, rect in enumerate(rectangles):
                self.assertAlmostEqual(rect.x0/mm, 12+slot%2*96, places=3)
                self.assertAlmostEqual(rect.y0/mm, 15.5+slot//2*136, places=3)
                for x, y in [(1.5, 65), (88.5, 65), (1.5, 115), (88.5, 115)]:
                    pixels = page.get_pixmap(clip=fitz.Rect(rect.x0+x*mm, rect.y0+y*mm, rect.x0+(x+.5)*mm, rect.y0+(y+.5)*mm))
                    self.assertTrue(all(abs(a-b)<=2 for a,b in zip(pixels.samples[:3], (23,74,52))))
