"""Generate both premium concepts without Django apps, .env or any database.

python -B scripts/generate_premium_badge_previews.py
Requires the existing backend/requirements-test-ids.txt packages.
No production renderer, route or credential is replaced or created.
"""
import base64
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))


def fixtures():
    from PIL import Image, ImageDraw
    portrait = Image.new('RGB', (280, 360), '#e0e6dc')
    draw = ImageDraw.Draw(portrait)
    draw.ellipse((38, 172, 242, 430), fill='#355e4c')
    draw.ellipse((88, 45, 192, 173), fill='#af8d71')
    draw.ellipse((100, 57, 184, 162), fill='#c8a68a')
    draw.text((65, 337), 'SYNTHETIC PORTRAIT', fill='#ffffff')
    data = io.BytesIO()
    portrait.save(data, format='PNG')
    photo = 'data:image/png;base64,'+base64.b64encode(data.getvalue()).decode()
    def card(index, assigned=True, long_name=False, with_photo=True, colour='#8f3c63'):
        return dict(synthetic=True, enrollment=SimpleNamespace(
            edition=SimpleNamespace(name='Darul Islam Camp 2026'),
            participant=SimpleNamespace(full_name=('SYNTHETIC '+('Abdulrahman Olayiwola Muhammad '*5) if long_name else f'SYNTHETIC Participant {index:02d}')),
            participant_number=f'SYNTHETIC-{index:04d}'),
            portrait=photo if with_photo else None, portrait_status='Photograph pending',
            house='SYNTHETIC HOUSE A' if assigned else 'Housing assignment pending',
            house_colour=colour if assigned else None, house_assigned=assigned,
            verification_url=f'https://example.invalid/dic/ids/verify/#SYNTHETIC-NOT-A-CREDENTIAL-{index:04d}')
    return {
        'single': [card(1)],
        'four-up': [card(1), card(2, assigned=False, with_photo=False), card(3, long_name=True), card(4, colour=None)],
        'assigned-house': [card(1)],
        'pending-house': [card(1, assigned=False, with_photo=False)],
        'long-name-photo': [card(1, long_name=True)],
        'batch-17-five-pages': [card(i+1, assigned=i%2 == 0, with_photo=i%3 != 1) for i in range(17)],
    }


def verify_pdf(payload, cards, concept, output, stem):
    import cv2
    import fitz
    import numpy as np
    from dic.premium_badge_concepts import CONCEPTS, GREEN, NAME_BOX, NAME_MINIMUM_PT
    from dic.portrait_pdf import mm
    document = fitz.open(stream=payload, filetype='pdf')
    if len(document) != (len(cards)+3)//4:
        raise AssertionError('Incorrect page count')
    pages, images = [], []
    for page_index, page in enumerate(document):
        assert page.rotation == 0
        assert abs(page.rect.width-210*mm)<.01 and abs(page.rect.height-297*mm)<.01
        drawings = page.get_drawings()
        rectangles = [d['rect'] for d in drawings if abs(d['rect'].width-90*mm)<.01 and abs(d['rect'].height-130*mm)<.01]
        count = min(4, len(cards)-page_index*4)
        assert len(rectangles) == count
        guides = [d['items'][0] for d in drawings if d['type'] == 's' and len(d['items']) == 1 and d['items'][0][0] == 'l']
        assert len(guides) == count*8
        bounds = []
        for slot, rect in enumerate(rectangles):
            left, top = 12+slot%2*96, 15.5+slot//2*136
            assert abs(rect.x0-left*mm)<.01 and abs(rect.y0-top*mm)<.01
            for cx, cy in [(left, top), (left+90, top), (left, top+130), (left+90, top+130)]:
                dx, dy = (-1 if cx == left else 1), (-1 if cy == top else 1)
                for line in [(cx+dx,cy,cx+2.5*dx,cy), (cx,cy+dy,cx,cy+2.5*dy)]:
                    assert any(all(abs(a-b*mm)<.02 for a,b in zip((*g[1],*g[2]),line)) for g in guides)
            qx, qt, qs = CONCEPTS[concept]['qr']
            qr_rect = fitz.Rect((left+qx)*mm, (top+qt)*mm, (left+qx+qs)*mm, (top+qt+qs)*mm)
            pix = page.get_pixmap(matrix=fitz.Matrix(6,6), clip=qr_rect)
            rgb = np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
            decoded,_,_ = cv2.QRCodeDetector().detectAndDecode(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
            assert decoded == cards[page_index*4+slot]['verification_url'], 'QR readability check failed'
            nx,nt,nw,nh = NAME_BOX
            name_area = fitz.Rect((left+nx)*mm,(top+nt)*mm,(left+nx+nw)*mm,(top+nt+nh)*mm)
            # Full-page extraction is deliberate: clipped extraction could hide overflow.
            name_spans = [span for block in page.get_text('dict')['blocks'] if 'lines' in block
                for line in block['lines'] for span in line['spans']
                if span['size'] >= NAME_MINIMUM_PT-.01 and name_area.intersects(fitz.Rect(span['bbox']))]
            assert name_spans, 'Participant name missing'
            expected_name = cards[page_index*4+slot]['enrollment'].participant.full_name
            assert ''.join(expected_name.split()) == ''.join(''.join(s['text'] for s in name_spans).split()), 'Participant name changed or truncated'
            for span in name_spans:
                sx0,sy0,sx1,sy1 = span['bbox']
                assert sx0 >= name_area.x0-.05 and sy0 >= name_area.y0-.05
                assert sx1 <= name_area.x1+.05 and sy1 <= name_area.y1+.05, 'Name exceeds its designated bounds'
            from dic.premium_badge_concepts import NEUTRAL
            expected_accent = cards[page_index*4+slot]['house_colour'] or NEUTRAL
            accent_rgb = tuple(v/255 for v in bytes.fromhex(expected_accent[1:]))
            assert any(d.get('fill') and len(d['fill']) == 3 and
                all(abs(a-b)<.002 for a,b in zip(d['fill'],accent_rgb)) and
                d['rect'].width >= 70*mm and d['rect'].x0 >= rect.x0+5*mm and
                d['rect'].x1 <= rect.x1-5*mm and d['rect'].y0 >= rect.y0+95*mm and d['rect'].y1 <= rect.y1-5*mm
                for d in drawings), 'House accent/neutral ribbon is missing or misplaced'
            for sx,sy in [(1.5,65),(88.5,65),(45,1.5),(1.5,115),(88.5,115),(45,128.5)]:
                pix = page.get_pixmap(matrix=fitz.Matrix(3,3),clip=fitz.Rect((left+sx)*mm,(top+sy)*mm,(left+sx+.5)*mm,(top+sy+.5)*mm))
                assert all(abs(a-b)<=2 for a,b in zip(pix.samples[:3],bytes.fromhex(GREEN[1:])))
            bounds.append([round(v/mm,3) for v in rect])
        image = output/f'{stem}-page-{page_index+1}.png'
        page.get_pixmap(matrix=fitz.Matrix(2,2)).save(image)
        images.append(image.name)
        pages.append(dict(badges=count,badge_bounds_mm=bounds,cutting_guides=len(guides),qr_decoded=count,names_within_bounds=count))
    # A large badge-only image makes the side-by-side comparison useful on screen.
    if len(cards) == 1:
        closeup = output/f'{stem}-badge.png'
        document[0].get_pixmap(matrix=fitz.Matrix(4,4),clip=fitz.Rect(12*mm,15.5*mm,102*mm,145.5*mm)).save(closeup)
        images.append(closeup.name)
    return dict(pages=pages,images=images)


def main():
    from django.conf import settings
    if settings.configured:
        raise RuntimeError('Run in a fresh standalone Python process.')
    settings.configure(USE_I18N=False,DATABASES={})
    from dic.premium_badge_concepts import CONCEPTS,render_concept_pdf
    output = ROOT/'output'/'pdf'/'dic-premium-concepts'
    output.mkdir(parents=True,exist_ok=True)
    (output/'verification.json').write_text(json.dumps(dict(automated='INCOMPLETE',visual_approval='PENDING',production_renderer_changed=False,database_access=False)),encoding='utf-8')
    groups = fixtures()
    report, gallery = [], []
    # No import of models, Django app setup, credential services or test runner.
    for concept, detail in CONCEPTS.items():
        gallery.append(f'<h2>{detail["label"]}</h2><div class="grid">')
        for scenario,cards in groups.items():
            stem = f'{concept}-{scenario}'
            payload = render_concept_pdf(cards,concept)
            target = output/f'{stem}.pdf'
            target.write_bytes(payload)
            result = verify_pdf(payload,cards,concept,output,stem)
            report.append(dict(concept=concept,scenario=scenario,pdf=str(target),cards=len(cards),**result))
            gallery.append(f'<figure><a href="{target.name}"><img src="{result["images"][0]}" alt="{detail["label"]}: {scenario}"></a><figcaption>{scenario} · <a href="{target.name}">A4 PDF</a></figcaption></figure>')
        gallery.append('</div>')
    from PIL import Image, ImageDraw
    a = Image.open(output/'classic-executive-single-badge.png').convert('RGB')
    b = Image.open(output/'modern-premium-single-badge.png').convert('RGB')
    comparison = Image.new('RGB',(a.width+b.width+120,max(a.height,b.height)+110),'#eeeade')
    comparison.paste(a,(40,70))
    comparison.paste(b,(a.width+80,70))
    draw = ImageDraw.Draw(comparison)
    draw.text((40,25),'CONCEPT A - CLASSIC EXECUTIVE',fill='#174a34')
    draw.text((a.width+80,25),'CONCEPT B - MODERN PREMIUM',fill='#174a34')
    comparison.save(output/'concept-comparison.png')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>DIC premium concept review</title><style>body{font:16px Arial;background:#eeeade;color:#174a34;margin:32px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}figure{margin:0}img{max-width:100%;height:auto}figcaption{padding:12px;background:white}</style><h1>DIC 2026 — two premium concepts</h1><p>Synthetic previews only. Production design has NOT been replaced. PDFs must be printed at actual size / 100%. Awaiting visual selection.</p><img src="concept-comparison.png" alt="Classic Executive and Modern Premium comparison">'+''.join(gallery),encoding='utf-8')
    (output/'verification.json').write_text(json.dumps(dict(automated='passed',visual_approval='PENDING',production_renderer_changed=False,database_access=False,fixtures=report),indent=2),encoding='utf-8')
    print('Premium concepts generated and automatic checks passed: '+str(output))
    print('Await visual review and concept selection; production rendering is unchanged.')


if __name__ == '__main__':
    main()
