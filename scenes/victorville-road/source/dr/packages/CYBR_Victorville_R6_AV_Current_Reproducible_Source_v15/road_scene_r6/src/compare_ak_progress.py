from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
r=Path(__file__).resolve().parents[1]
a=Image.open(r/'captures/aj_retained_stock_context_preview/CLEAN_OIDN_PANEL.png').convert('RGB')
b=Image.open(r/'captures/ak_substrate_units_context_preview/CLEAN_OIDN_PANEL.png').convert('RGB')
assert a.size==b.size
w,h=a.size;out=Image.new('RGB',(w*2,h+56),(24,27,31));out.paste(a,(0,56));out.paste(b,(w,56));draw=ImageDraw.Draw(out);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',21)
draw.text((18,16),'AJ: recent sediment event only',font=font,fill=(245,245,245))
draw.text((w+18,16),'AK: pre-existing sand, compacted fines and gravel',font=font,fill=(245,245,245))
out.save(r/'deliverables/CYBR_Victorville_AK_Substrate_History_Comparison.png')
