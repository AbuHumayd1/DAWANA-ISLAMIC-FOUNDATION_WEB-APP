"""Seven hybrid scenarios and a three-concept comparison. No database or app setup."""
import copy
import json
from pathlib import Path
import sys
from generate_premium_badge_previews import fixtures, verify_pdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def main():
    import fitz
    from PIL import Image,ImageDraw,ImageFont
    from django.conf import settings
    if settings.configured:
        raise RuntimeError('Use a fresh standalone Python process.')
    settings.configure(USE_I18N=False,DATABASES={})
    from dic.premium_hybrid_badge import render_hybrid_pdf,QR,NAME_BOX
    from dic.premium_badge_concepts import render_concept_pdf,CONCEPTS,NAME_BOX as ORIGINAL_NAME_BOX
    from dic.portrait_pdf import mm
    assert QR == CONCEPTS['modern-premium']['qr'] and NAME_BOX == ORIGINAL_NAME_BOX
    original = fixtures()
    assigned = original['assigned-house'][0]
    missing = {**copy.deepcopy(assigned),'portrait':None,'portrait_status':'Photograph pending'}
    groups = {
        'hybrid-assigned-house': [copy.deepcopy(assigned)],
        'hybrid-housing-pending': copy.deepcopy(original['pending-house']),
        'hybrid-with-photograph': [copy.deepcopy(assigned)],
        'hybrid-without-photograph': [missing],
        'hybrid-exceptionally-long-name': copy.deepcopy(original['long-name-photo']),
        'hybrid-four-up': copy.deepcopy(original['four-up']),
        'hybrid-batch-17-five-pages': copy.deepcopy(original['batch-17-five-pages']),
    }
    output = ROOT/'output'/'pdf'/'dic-premium-hybrid'
    output.mkdir(parents=True,exist_ok=True)
    manifest = output/'verification.json'
    manifest.write_text(json.dumps(dict(automated='INCOMPLETE',visual_approval='PENDING',database_access=False)),encoding='utf-8')
    reports,gallery = [],[]
    for stem,cards in groups.items():
        placements = []
        payload = render_hybrid_pdf(cards,placements=placements)
        path = output/f'{stem}.pdf'
        path.write_bytes(payload)
        # Reuse actual PDF verification with the unchanged Modern QR/name geometry;
        # this does not mutate either original concept or call its renderer.
        checks = verify_pdf(payload,cards,'modern-premium',output,stem)
        reports.append(dict(concept='final-premium-hybrid',pdf=str(path),cards=len(cards),placements=placements,**checks))
        gallery.append(f'<figure><a href="{path.name}"><img src="{checks["images"][0]}" alt="{stem}"></a><figcaption>{stem}</figcaption></figure>')
    # Render the old concepts only into new comparison files, never overwrite their folders.
    comparisons = []
    for key,label in [('classic-executive','Classic Executive'),('modern-premium','Modern Premium'),('hybrid','Final Premium Hybrid')]:
        cards = [copy.deepcopy(assigned)]
        payload = render_hybrid_pdf(cards) if key == 'hybrid' else render_concept_pdf(cards,key)
        document = fitz.open(stream=payload,filetype='pdf')
        png = output/f'comparison-{key}.png'
        document[0].get_pixmap(matrix=fitz.Matrix(4,4),clip=fitz.Rect(12*mm,15.5*mm,102*mm,145.5*mm)).save(png)
        comparisons.append((label,Image.open(png).convert('RGB')))
    w,h = comparisons[0][1].size
    comparison = Image.new('RGB',(3*w+160,h+110),'#eeeade')
    draw = ImageDraw.Draw(comparison)
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',25)
    except OSError:
        font = ImageFont.load_default(size=25)
    for index,(label,image) in enumerate(comparisons):
        x = 40+index*(w+40)
        comparison.paste(image,(x,70))
        draw.text((x,24),label,fill='#174a34',font=font)
    comparison.save(output/'three-concept-comparison.png')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>DIC premium hybrid review</title><style>body{font:16px Arial;background:#eeeade;color:#174a34;margin:32px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}figure{margin:0}img{max-width:100%;height:auto}figcaption{padding:10px;background:white}</style><h1>Final Premium Hybrid — preview only</h1><p>Production and the previous concepts are unchanged. Synthetic data only. Actual-size printing: 100%. Awaiting visual approval.</p><img src="three-concept-comparison.png" alt="Classic Executive, Modern Premium and Final Premium Hybrid"><div class="grid">'+''.join(gallery)+'</div>',encoding='utf-8')
    manifest.write_text(json.dumps(dict(automated='passed',visual_approval='PENDING',database_access=False,production_changed=False,previous_concepts_changed=False,fixtures=reports),indent=2),encoding='utf-8')
    print('Hybrid review artifacts and geometric/QR/name checks: '+str(output))
    print('Visual acceptance remains pending. Production rendering has not changed.')


if __name__ == '__main__':
    main()
