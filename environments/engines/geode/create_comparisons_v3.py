"""Only annotate/resize already rendered pixels. Never generate scene imagery."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output_v3'
font_path='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
try:font=ImageFont.truetype(font_path,18);small=ImageFont.truetype(font_path,14)
except OSError:font=ImageFont.load_default();small=font

def filter_check():
    a=Image.open(OUT/'detail_filter_before.png').convert('RGB')
    b=Image.open(OUT/'detail_filter_after.png').convert('RGB')
    crop=(27,85,348,280)
    a=a.crop(crop).resize((642,390),Image.Resampling.NEAREST)
    b=b.crop(crop).resize((642,390),Image.Resampling.NEAREST)
    sheet=Image.new('RGB',(1312,482),(19,24,30));d=ImageDraw.Draw(sheet)
    d.text((14,12),'Same raw 8-sample frame | 2× nearest-neighbor pixel inspection',font=font,fill=(235,237,239))
    d.text((14,42),'Previous asymmetric weights',font=small,fill=(220,223,228))
    d.text((663,42),'Corrected symmetric log-variance weights',font=small,fill=(220,223,228))
    sheet.paste(a,(14,67));sheet.paste(b,(663,67))
    d.text((14,461),'No highlight clamp in either image. This tests the filter artifact, not transport convergence.',font=small,fill=(190,196,204))
    sheet.save(OUT/'Drowned_Geode_V3_Filter_Artifact_Check.png')

def overview():
    old=ROOT/'assets/comparison/Drowned_Geode_V2.png';new=OUT/'Drowned_Geode_V3.png'
    if not old.exists() or not new.exists():return
    sheet=Image.new('RGB',(1840,700),(19,24,30));d=ImageDraw.Draw(sheet)
    for x,p,label in [(20,old,'V2 — previous delivered scene'),(930,new,'V3 — rebuilt cavern and quartz transport')]:
        im=Image.open(p).convert('RGB');im.thumbnail((890,610),Image.Resampling.LANCZOS)
        d.text((x,16),label,font=font,fill=(234,237,241));sheet.paste(im,(x+(890-im.width)//2,52+(610-im.height)//2))
    d.text((20,678),'Different geometry, lighting, framing and sampling; this is a scene comparison, not an equal-scene noise benchmark.',font=small,fill=(190,196,204))
    sheet.save(OUT/'Drowned_Geode_V3_Before_After.png')

if __name__=='__main__':filter_check();overview()
