from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
r=Path(__file__).resolve().parents[1]
a=Image.open(r/'captures/ak_substrate_units_detail/CLEAN_OIDN_PANEL.png').convert('RGB').crop((0,60,1000,250));b=Image.open(r/'captures/al_film_ownership_detail/CLEAN_OIDN_PANEL.png').convert('RGB').crop((0,60,1000,250));w,h=a.size
out=Image.new('RGB',(w*2,h+56),(24,27,31));out.paste(a,(0,56));out.paste(b,(w,56));d=ImageDraw.Draw(out);f=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',20)
d.text((18,15),'AK: soil stock also shaded on exposed asphalt',font=f,fill=(245,245,245));d.text((w+18,15),'AL control: only pavement-owned stock',font=f,fill=(245,245,245));out.save(r/'deliverables/CYBR_Victorville_AL_Film_Ownership_Control.png')
