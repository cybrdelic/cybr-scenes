"""Create a portable historical AH/AI comparison after both captures exist."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[1]

def main():
    a=Image.open(ROOT/'captures/ah_d_integrated_bank_context_preview/CLEAN_OIDN_PANEL.png').convert('RGB')
    b=Image.open(ROOT/'captures/ai_sorted_support_context_preview/CLEAN_OIDN_PANEL.png').convert('RGB')
    if a.size != b.size:raise ValueError('Matched resolution required')
    w,h=a.size;out=Image.new('RGB',(w*2,h+56),(24,27,31));out.paste(a,(0,56));out.paste(b,(w,56))
    draw=ImageDraw.Draw(out)
    try:font=ImageFont.truetype('DejaVuSans.ttf',21)
    except OSError:font=ImageFont.load_default()
    draw.text((18,16),'AH: authored contact pockets',font=font,fill=(245,245,245))
    draw.text((w+18,16),'AI: bank-supported edge + flow-linked grain exposure',font=font,fill=(245,245,245))
    target=ROOT/'deliverables/CYBR_Victorville_AI_Sorted_Support_Comparison.png'
    target.parent.mkdir(parents=True,exist_ok=True);out.save(target)

if __name__=='__main__':main()
