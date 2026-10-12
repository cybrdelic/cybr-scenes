from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import hashlib,json
r=Path(__file__).resolve().parents[1]
rows=[('AL: previous supported shoulder', 'al_supported_ownership_context'),('AP: correlated fine/gravel margin and layered scrub', 'ap_correlated_margin_context')]
canvas=Image.new('RGB',(2000,729),(23,26,30));d=ImageDraw.Draw(canvas);f=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',22);small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',16);records=[]
for i,(label,folder) in enumerate(rows):
 p=r/'captures'/folder/'CLEAN_OIDN_PANEL.png';im=Image.open(p).convert('RGB');assert im.size==(1000,667);d.text((i*1000+12,8),label,font=f,fill=(240,240,240));canvas.paste(im,(i*1000,36));records.append({'capture':folder,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
d.text((12,709),'Matched camera and daylight; actual CPU renders. AP is an authored historical distribution, not a surveyed site or validated sediment model.',font=small,fill=(215,220,225))
p=r/'deliverables/CYBR_Victorville_AP_Road_Margin_Comparison.png';canvas.save(p)
(r/'receipts/ap_visual_comparison.json').write_text(json.dumps({'comparison_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'inputs':records,'resized':False,'whole_scene_accepted_by_user':False},indent=2))
