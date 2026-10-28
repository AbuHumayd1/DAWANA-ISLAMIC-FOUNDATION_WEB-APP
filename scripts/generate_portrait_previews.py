"""Synthetic portrait QA through the production renderer. NO Django setup or DB.

Run: python -B scripts/generate_portrait_previews.py
Only local output files are written; no issuance service or QR token generator is used.
"""
import base64
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def main():
    import cv2
    import fitz
    import numpy as np
    from PIL import Image, ImageDraw
    from django.conf import settings
    if settings.configured:
        raise RuntimeError('Run this standalone script in a fresh Python process.')
    # No .env, installed apps, django.setup(), models, DB connections or test runner.
    settings.configure(USE_I18N=False, DATABASES={})
    from dic.portrait_pdf import render_pdf, geometry, mm
    from dic.premium_hybrid_badge import QR
    from dic.premium_badge_concepts import NEUTRAL
    from dic.identity_branding import official_logo_data
    if not official_logo_data():
        raise RuntimeError('Restore the cached official logo before design review.')
    assert geometry() == (90*mm, 130*mm, 6*mm)
    output = ROOT / 'output' / 'pdf' / 'dic-portrait-stage1'
    output.mkdir(parents=True, exist_ok=True)

    portrait = Image.new('RGB', (280, 360), '#e7ede7')
    draw = ImageDraw.Draw(portrait)
    draw.ellipse((85, 48, 195, 170), fill='#b29379')
    draw.ellipse((38, 178, 242, 420), fill='#365c49')
    draw.text((70, 332), 'SYNTHETIC PORTRAIT', fill='#ffffff')
    buffer = io.BytesIO()
    portrait.save(buffer, format='PNG')
    photo = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()

    def card(index, assigned=False, long_name=False, with_photo=False, unconfigured=False):
        # Explicit synthetic fixture configuration, never official house data.
        house = SimpleNamespace(name='SYNTHETIC HOUSE A', badge_colour=None if unconfigured else '#8f3c63') if assigned else None
        person = SimpleNamespace(full_name=('SYNTHETIC Abdulrahman Olayiwola Muhammad Abdulazeez Adebayo' if long_name else f'SYNTHETIC Participant {index:02d}'))
        enrollment = SimpleNamespace(participant=person, participant_number=f'SYNTHETIC-{index:04d}',
            edition=SimpleNamespace(name='Darul Islam Camp 2026'), fixture_house=house)
        return dict(enrollment=enrollment, portrait=photo if with_photo else None,
            portrait_status='Photograph pending', synthetic=True,
            verification_url=f'https://example.invalid/dic/ids/verify/#SYNTHETIC-NOT-A-CREDENTIAL-{index:04d}')

    groups = {
        'portrait-single': [card(1, with_photo=True)],
        'portrait-four-up': [card(1, True, with_photo=True), card(2), card(3, True, True, True), card(4, True, unconfigured=True)],
        'portrait-configured-house': [card(1, True, with_photo=True)],
        'portrait-pending-house': [card(1)],
        'portrait-long-name-photo': [card(1, True, True, True)],
        'portrait-batch-17-five-pages': [card(i+1, assigned=i%2 == 0, with_photo=i%3 == 0) for i in range(17)],
    }
    def fixture_house(enrollment):
        house = enrollment.fixture_house
        return (house.name, house.badge_colour) if house else ('Housing assignment pending', None)

    report, gallery = [], []
    for name, cards in groups.items():
        with patch('dic.portrait_pdf.house_details', side_effect=fixture_house):
            payload = render_pdf(cards)
        target = output / f'{name}.pdf'
        target.write_bytes(payload)
        document = fitz.open(stream=payload, filetype='pdf')
        assert len(document) == (len(cards)+3)//4
        pages = []
        for page_index, page in enumerate(document):
            assert page.rotation == 0
            assert abs(page.rect.width-210*mm)<.01 and abs(page.rect.height-297*mm)<.01
            drawings = page.get_drawings()
            badge_rects = [d['rect'] for d in drawings if abs(d['rect'].width-90*mm)<.01 and abs(d['rect'].height-130*mm)<.01]
            count = min(4, len(cards)-page_index*4)
            assert len(badge_rects) == count
            guides = [d['items'][0] for d in drawings if d['type'] == 's' and len(d['items']) == 1 and d['items'][0][0] == 'l']
            assert len(guides) == count*8
            bounds = []
            for slot, rect in enumerate(badge_rects):
                left, top = 12+(slot%2)*96, 15.5+(slot//2)*136
                assert abs(rect.x0-left*mm)<.01 and abs(rect.y0-top*mm)<.01
                expected = []
                for cx, cy in [(left, top), (left+90, top), (left, top+130), (left+90, top+130)]:
                    dx, dy = (-1 if cx == left else 1), (-1 if cy == top else 1)
                    expected.extend([(cx+dx, cy, cx+dx*2.5, cy), (cx, cy+dy, cx, cy+dy*2.5)])
                for line in expected:
                    assert any(all(abs(a-b*mm)<.02 for a,b in zip((*g[1], *g[2]), line)) for g in guides)
                qx,qt,qs = QR
                crop = fitz.Rect((left+qx)*mm, (top+qt)*mm, (left+qx+qs)*mm, (top+qt+qs)*mm)
                pix = page.get_pixmap(matrix=fitz.Matrix(5, 5), clip=crop)
                rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
                assert decoded == cards[page_index*4+slot]['verification_url'], 'QR decoding failed'
                # Confirm green frame remains at all four edges, including house level.
                for sx, sy in [(1.5, 65), (88.5, 65), (45, 1.5), (1.5, 115), (88.5, 115)]:
                    sample = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=fitz.Rect((left+sx)*mm, (top+sy)*mm, (left+sx+.5)*mm, (top+sy+.5)*mm))
                    assert max(abs(a-b) for a,b in zip(sample.samples[:3], (23,74,52))) <= 2
                house = cards[page_index*4+slot]['enrollment'].fixture_house
                accent = house.badge_colour if house else None
                expected_rgb = tuple(bytes.fromhex((accent or NEUTRAL)[1:]))
                ribbons = [drawing['rect'] for drawing in drawings if drawing.get('fill')
                    and all(abs(a-b/255)<.002 for a,b in zip(drawing['fill'],expected_rgb))
                    and abs(drawing['rect'].width-74*mm)<.02
                    and drawing['rect'].x0 >= rect.x0+7*mm
                    and drawing['rect'].x1 <= rect.x1-7*mm
                    and drawing['rect'].y0 >= rect.y0+95*mm
                    and drawing['rect'].y1 <= rect.y1-5*mm]
                assert len(ribbons) == 1
                ribbon = ribbons[0]
                sample = page.get_pixmap(matrix=fitz.Matrix(3,3),clip=fitz.Rect(ribbon.x0+1.5*mm,(ribbon.y0+ribbon.y1)/2,ribbon.x0+1.9*mm,(ribbon.y0+ribbon.y1)/2+.4*mm))
                assert max(abs(a-b) for a,b in zip(sample.samples[:3], expected_rgb)) <= 2
                bounds.append([round(v/mm, 3) for v in rect])
            png = output / f'{name}-page-{page_index+1}.png'
            page.get_pixmap(matrix=fitz.Matrix(2, 2)).save(png)
            gallery.append(f'<figure><a href="{target.name}"><img src="{png.name}" alt="{name}, page {page_index+1}"></a><figcaption>{name} / page {page_index+1}</figcaption></figure>')
            pages.append(dict(badge_count=count, badge_bounds_mm=bounds, cutting_guides=len(guides), qr_decoded=count))
        report.append(dict(pdf=target.name, cards=len(cards), pages=pages))
    (output / 'verification.json').write_text(json.dumps(dict(automated='passed', visual_acceptance='PENDING HUMAN REVIEW', database_access=False, fixtures=report), indent=2))
    (output / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>DIC portrait badge review</title><style>body{background:#eeeade;font:16px Arial;margin:32px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:24px}figure{margin:0}img{width:100%;height:auto}figcaption{padding:12px;background:white}</style><h1>DIC 2026 portrait badge review</h1><p>Synthetic only. Not valid credentials. Open a PDF and print at actual size / 100%. Automated checks do not constitute visual approval.</p><main>'+''.join(gallery)+'</main>', encoding='utf-8')
    print('Synthetic previews and automated verification: ' + str(output))
    print('Visual acceptance: PENDING HUMAN REVIEW')


if __name__ == '__main__':
    main()
