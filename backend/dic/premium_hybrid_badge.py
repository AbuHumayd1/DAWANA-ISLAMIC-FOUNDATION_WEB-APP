"""Approved hybrid drawing shared by authorized production and synthetic previews."""
import io
import math
import re
import unicodedata
from dataclasses import dataclass
from xml.sax.saxutils import escape
from .premium_badge_concepts import BadgePainter, register_fonts, GREEN, DEEP, GOLD, CREAM, NEUTRAL
from .portrait_pdf import geometry, mm, A4, require_pdf_dependencies
from .identity_branding import official_logo_data

LABEL = 'Final Premium Hybrid'
QR = (49, 37, 33)
NAME_BOX = (7, 76, 76, 28)
MIN_NAME_PT = 11


@dataclass(frozen=True)
class NameLayout:
    lines: tuple
    font_size: float
    height_mm: float


def _split_word(word, width, measure):
    """Only oversized words are split; keep combining marks with their base."""
    clusters = []
    for char in word:
        if unicodedata.combining(char) and clusters:
            clusters[-1] += char
        else:
            clusters.append(char)
    if measure(word) <= width:
        return [word]
    count = max(2, math.ceil(measure(word)/width))
    while count <= len(clusters):
        parts, offset = [], 0
        for remaining in range(count, 1, -1):
            target = measure(''.join(clusters[offset:]))/remaining
            choices = []
            for end in range(offset+1, len(clusters)-remaining+2):
                part = ''.join(clusters[offset:end])
                used = measure(part)
                if used > width:
                    break
                choices.append((abs(used-target), end, part))
            if not choices:
                break
            _, offset, part = min(choices)
            parts.append(part)
        tail = ''.join(clusters[offset:])
        if len(parts) == count-1 and tail and measure(tail) <= width:
            return parts+[tail]
        count += 1
    raise ValueError('A name glyph exceeds the readable name width.')


def plan_name(value):
    """Measure actual font advances; prefer readable single lines, then balanced words."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    register_fonts()
    name = ' '.join(str(value).split())
    if not name:
        raise ValueError('A participant name is required.')
    width, height = (NAME_BOX[2]-1)*mm, (NAME_BOX[3]-1)*mm
    for step in range(12+1):
        size = 19-step*.25
        if stringWidth(name,'PremiumBold',size) <= width:
            return NameLayout((name,),size,size*1.12/mm)
    for step in range(int((19-MIN_NAME_PT)*4)+1):
        size = 19-step*.25
        measure = lambda text: stringWidth(text,'PremiumBold',size)
        tokens = []
        for word in name.split():
            for part_index, part in enumerate(_split_word(word,width,measure)):
                tokens.append((part,' ' if part_index == 0 else ''))
        max_lines = int((height+.001)/(size*1.12))
        # (token end, line count) -> (raggedness cost, rendered lines).
        best = {(0,0):(0,())}
        for end in range(1,len(tokens)+1):
            for start in range(end):
                line = ''.join((join if index > start else '')+text
                    for index,(text,join) in enumerate(tokens[start:end],start))
                used = measure(line)
                if used > width+.001:
                    continue
                penalty = (width-used)**2
                if end == len(tokens) and (len(line.strip()) <= 3 or line.strip().isdigit()):
                    penalty += width**2*20
                for count in range(1,max_lines+1):
                    previous = best.get((start,count-1))
                    if previous is None:
                        continue
                    candidate = (previous[0]+penalty, previous[1]+(line,))
                    key = (end,count)
                    if key not in best or candidate[0] < best[key][0]:
                        best[key] = candidate
        candidates = []
        for count in range(1,max_lines+1):
            fitted = best.get((len(tokens),count))
            if fitted:
                last = fitted[1][-1].strip()
                orphan = count > 1 and (len(last) <= 3 or last.isdigit())
                candidates.append((orphan,count,fitted[0],fitted[1]))
        if candidates:
            _,count,_,lines = min(candidates)
            return NameLayout(lines,size,count*size*1.12/mm)
    raise ValueError('Name requires manual layout review at the 11 pt readability minimum; no text was truncated.')


def _draw_name(pdf, value):
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor
    fit = plan_name(value)
    # Center the compact lower cluster in the available body space for short names.
    used = fit.height_mm+1
    ribbon_height = min(12,48-used-10)
    if ribbon_height < 9:
        raise ValueError('Insufficient house-ribbon space at a readable name size.')
    name_top = NAME_BOX[1]+max(0,(48-used-10-ribbon_height)/2)
    style = ParagraphStyle('hybrid-name',fontName='PremiumBold',fontSize=fit.font_size,
        leading=fit.font_size*1.12,textColor=HexColor(GREEN),alignment=0,
        splitLongWords=False,spaceShrinkage=0)
    paragraph = Paragraph('<br/>'.join(escape(line) for line in fit.lines),style)
    _, actual = paragraph.wrap((NAME_BOX[2]-1)*mm,(NAME_BOX[3]-1)*mm)
    if actual > (NAME_BOX[3]-1)*mm+.01 or abs(actual/mm-fit.height_mm)>.01:
        raise ValueError('Measured name wrapping differs from the planned layout.')
    paragraph.drawOn(pdf,(NAME_BOX[0]+.5)*mm,(130-name_top-.5)*mm-actual)
    label_top = name_top+used+1
    number_top = label_top+3
    house_top = number_top+6
    return dict(name_box=NAME_BOX,name_top=name_top,name_height=used,name_size=fit.font_size,
        name_lines=fit.lines,label_top=label_top,number_top=number_top,
        house_top=house_top,house_height=ribbon_height)


def render_hybrid_pdf(cards, *, placements=None):
    """Synthetic-only preview entry point, retained for comparison tooling."""
    if not cards or any(card.get('synthetic') is not True for card in cards):
        raise ValueError('Use the authorized portrait workflow for participant cards.')
    return _render_hybrid_pdf(cards, placements=placements)


def _render_hybrid_pdf(cards, *, placements=None):
    """Internal drawing only; production authority is established by existing callers."""
    require_pdf_dependencies()
    from reportlab.pdfgen import canvas
    register_fonts()
    logo = official_logo_data()
    if not logo:
        raise ValueError('The unchanged official logo asset is required.')
    width,height,gap = geometry()
    output = io.BytesIO()
    pdf = canvas.Canvas(output,pagesize=A4,pageCompression=1)
    pdf.setTitle('DIC 2026 - Final Premium Hybrid')
    for index,card in enumerate(cards):
        if index and index%4 == 0:
            pdf.showPage()
        pdf.saveState()
        x = (A4[0]-2*width-gap)/2+index%2*(width+gap)
        y = A4[1]-(A4[1]-2*height-gap)/2-height-(index%4//2)*(height+gap)
        pdf.translate(x,y)
        p = BadgePainter(pdf)
        p.box(0,0,90,130,GREEN)
        p.box(3,3,84,124,CREAM)
        pdf.setStrokeColor(p.colour(GOLD))
        pdf.setLineWidth(.16*mm)
        pdf.roundRect(3.7*mm,3.7*mm,82.6*mm,122.6*mm,1.5*mm,fill=0,stroke=1)
        p.box(4,4,82,27,DEEP)
        p.logo(logo,False)
        p.text('DAWANA ISLAMIC FOUNDATION',32,9,49,9,size=11,minimum=11,colour=CREAM,font='PremiumBold',align=0)
        p.text(card['enrollment'].edition.name,32,23,49,5,size=8.3,minimum=8.3,colour='#ddc58b',align=0)
        p.box(8,32,74,.3,GOLD)
        p.portrait(card,8,35,34,39,False)
        pdf.setStrokeColor(p.colour(GOLD))
        pdf.setLineWidth(.12*mm)
        pdf.roundRect(8.6*mm,56.6*mm,32.8*mm,37.8*mm,1.4*mm,fill=0,stroke=1)
        # The existing Modern QR pixels, payload, size and quiet zone are reused.
        p.qr(card,'modern-premium')
        record = _draw_name(pdf,card['enrollment'].participant.full_name)
        p.text('PARTICIPANT NUMBER',8,record['label_top'],74,3,size=6.5,minimum=6.5,align=0)
        p.text(card['enrollment'].participant_number,8,record['number_top'],74,5,size=10.5,minimum=9,font='PremiumBold',align=0)
        raw = card.get('house_colour')
        accent = raw if isinstance(raw,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',raw) else None
        top,h = record['house_top'],record['house_height']
        p.box(8,top,74,h,accent or NEUTRAL,radius=1.4)
        p.box(11,top+.6,68,h-1.2,CREAM,radius=.8)
        p.text('HOUSE' if card.get('house_assigned') else 'HOUSING STATUS',13,top+1.1,64,2.7,size=6.3,minimum=6.3,align=0)
        p.text(card['house'],13,top+4,64,h-4.8,size=11,minimum=9.5,font='PremiumBold',align=0)
        if card.get('synthetic') is True:
            p.text('SYNTHETIC CONCEPT - NOT A VALID ID',8,125,74,1.8,size=4.5,minimum=4.5)
        pdf.setStrokeColor(p.colour('#777777'))
        pdf.setLineWidth(.25)
        for cx,cy in [(0,0),(width,0),(0,height),(width,height)]:
            dx,dy = (-1 if cx == 0 else 1),(-1 if cy == 0 else 1)
            pdf.line(cx+dx*mm,cy,cx+dx*2.5*mm,cy)
            pdf.line(cx,cy+dy*mm,cx,cy+dy*2.5*mm)
        pdf.restoreState()
        if placements is not None:
            placements.append(dict(index=index,page=index//4,slot=index%4,**record))
    pdf.save()
    return output.getvalue()
