"""Review-concept tests only. SimpleTestCase forbids database access."""
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from .premium_badge_concepts import CONCEPTS, render_concept_pdf, BadgePainter, NAME_BOX, NAME_MINIMUM_PT
from .portrait_pdf import mm


class PremiumBadgeConceptTests(SimpleTestCase):
    def card(self, index, long=False):
        return dict(synthetic=True, enrollment=SimpleNamespace(
            edition=SimpleNamespace(name='Darul Islam Camp 2026'),
            participant_number=f'SYNTHETIC-{index:04d}',
            participant=SimpleNamespace(full_name='SYNTHETIC '+('Abdulrahman Olayiwola Muhammad '*5 if long else f'Participant {index}'))),
            portrait=None,portrait_status='Photograph pending',house='Housing assignment pending',
            house_colour=None,house_assigned=False,verification_url=f'https://example.invalid/synthetic/{index}')

    def test_candidates_reject_non_synthetic_contexts_and_invalid_selectors(self):
        for concept in CONCEPTS:
            with self.assertRaises(ValueError):
                render_concept_pdf([{**self.card(1),'synthetic':False}],concept)
        with self.assertRaises(ValueError):
            render_concept_pdf([self.card(1)],'unapproved-selector')

    def test_both_concepts_have_four_exact_badges_and_partial_final_page(self):
        import fitz
        for concept in CONCEPTS:
            cards = [self.card(i+1,long=i == 0) for i in range(5)]
            pdf = fitz.open(stream=render_concept_pdf(cards,concept),filetype='pdf')
            self.assertEqual(len(pdf),2)
            for page_index,page in enumerate(pdf):
                self.assertAlmostEqual(page.rect.width/mm,210,places=3)
                self.assertAlmostEqual(page.rect.height/mm,297,places=3)
                self.assertEqual(page.rotation,0)
                bounds = [d['rect'] for d in page.get_drawings() if abs(d['rect'].width-90*mm)<.01 and abs(d['rect'].height-130*mm)<.01]
                self.assertEqual(len(bounds),4 if page_index == 0 else 1)
                for slot,rect in enumerate(bounds):
                    self.assertAlmostEqual(rect.x0/mm,12+slot%2*96,places=3)
                    self.assertAlmostEqual(rect.y0/mm,15.5+slot//2*136,places=3)
            # The name block must not quietly use tiny type for the long-name fixture.
            text = pdf[0].get_text('dict',clip=fitz.Rect(20*mm,93.5*mm,94*mm,116.5*mm))
            name_spans = [span for block in text['blocks'] if 'lines' in block for line in block['lines'] for span in line['spans']
                if any(word in span['text'] for word in ('Abdulrahman','Olayiwola','Muhammad'))]
            self.assertTrue(name_spans)
            self.assertTrue(all(span['size']>=10.99 for span in name_spans))
            self.assertIn(' '.join(cards[0]['enrollment'].participant.full_name.split()),' '.join(pdf[0].get_text().split()))

    def test_both_concepts_keep_existing_qr_payload_scannable(self):
        import cv2
        import fitz
        import numpy as np
        card = self.card(1)
        for concept,details in CONCEPTS.items():
            pdf = fitz.open(stream=render_concept_pdf([card],concept),filetype='pdf')
            x,top,size = details['qr']
            pixels = pdf[0].get_pixmap(matrix=fitz.Matrix(6,6),clip=fitz.Rect((12+x)*mm,(15.5+top)*mm,(12+x+size)*mm,(15.5+top+size)*mm))
            rgb = np.frombuffer(pixels.samples,dtype=np.uint8).reshape(pixels.height,pixels.width,pixels.n)
            decoded,_,_ = cv2.QRCodeDetector().detectAndDecode(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
            self.assertEqual(decoded,card['verification_url'])

    def test_name_variants_fit_without_clipping_or_overlapping_neighbouring_sections(self):
        import fitz
        cases = {
            'short': 'SYNTHETIC Ali',
            # Keep the exact 165-character fixture, including its trailing space.
            'original-long-fixture': self.card(1,long=True)['enrollment'].participant.full_name,
            'multiple-word': 'SYNTHETIC Amina Mariam Olayiwola Abdulrahman Muhammad Adebayo',
            'unusually-long-word': 'SYNTHETIC '+('AbdulrahmanOlayiwolaMuhammadAbdulazeezAdebayo'*2)+' Participant',
        }
        original_text = BadgePainter.text
        for concept in CONCEPTS:
            for scenario,name in cases.items():
                with self.subTest(concept=concept,name_case=scenario):
                    card = self.card(1)
                    card['enrollment'].participant.full_name = name
                    measured = {}
                    targets = (name,'PARTICIPANT NUMBER',card['enrollment'].participant_number)
                    def capture(painter,value,x,top,width,max_height,*args,**kwargs):
                        used = original_text(painter,value,x,top,width,max_height,*args,**kwargs)
                        if value in targets:
                            measured[value] = dict(x=x,top=top,width=width,max_height=max_height,used=used)
                        return used
                    with patch.object(BadgePainter,'text',new=capture):
                        document = fitz.open(stream=render_concept_pdf([card],concept),filetype='pdf')
                    record = measured[name]
                    self.assertLessEqual(record['used'],record['max_height']+.001)
                    nx,nt,nw,nh = NAME_BOX
                    allocated = fitz.Rect((12+nx)*mm,(15.5+nt)*mm,(12+nx+nw)*mm,(15.5+nt+nh)*mm)
                    # Select from full-page extraction, never a clipped text query:
                    # otherwise overflowing glyphs could silently disappear from the assertion.
                    selection = fitz.Rect((12+record['x']-.5)*mm,(15.5+record['top']-.5)*mm,
                        (12+record['x']+record['width']+.5)*mm,
                        (15.5+record['top']+record['used']+.8)*mm)
                    spans = [span for block in document[0].get_text('dict')['blocks'] if 'lines' in block
                        for line in block['lines'] for span in line['spans']
                        if selection.intersects(fitz.Rect(span['bbox']))]
                    self.assertTrue(spans)
                    for span in spans:
                        self.assertGreaterEqual(span['size'],NAME_MINIMUM_PT-.01)
                        x0,y0,x1,y1 = span['bbox']
                        self.assertGreaterEqual(x0,allocated.x0-.05)
                        self.assertGreaterEqual(y0,allocated.y0-.05)
                        self.assertLessEqual(x1,allocated.x1+.05)
                        self.assertLessEqual(y1,allocated.y1+.05)
                    # Splitting a long individual word may introduce line breaks,
                    # but every original character must remain in order.
                    self.assertEqual(''.join(name.split()),''.join(''.join(s['text'] for s in spans).split()))
                    if scenario != 'short':
                        self.assertGreater(len(spans),1)
                    label = measured['PARTICIPANT NUMBER']
                    number = measured[card['enrollment'].participant_number]
                    self.assertLess(record['top']+record['used']+.8,label['top'])
                    self.assertLess(label['top']+label['used'],number['top'])
                    house_top = max(100,number['top']+6)
                    self.assertLess(number['top']+number['used'],house_top)
                    qx,qt,qs = CONCEPTS[concept]['qr']
                    self.assertGreaterEqual(nt,qt+qs+5+1)
                    self.assertGreaterEqual(124-house_top,9)
