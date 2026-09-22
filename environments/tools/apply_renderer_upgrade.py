#!/usr/bin/env python3
"""Apply audited source patches to the recovered renderer families, once."""
from pathlib import Path
import shutil,json,difflib
ROOT=Path(__file__).resolve().parents[1]
changes=[]
def edit(relative,fn):
 p=ROOT/relative;original=p.read_text();backup=ROOT/'provenance/native-before'/relative
 if backup.exists():original=backup.read_text()
 else:backup.parent.mkdir(parents=True,exist_ok=True);backup.write_text(original)
 modified=fn(original)
 if modified==original:raise RuntimeError(f'No patch applied: {p}')
 p.write_text(modified)
 changes.append({'file':relative,'changed_lines':sum(1 for l in difflib.ndiff(original.splitlines(),modified.splitlines()) if l[:1] in '+-')})
 return modified

def replace(s,a,b):
 if a not in s:raise RuntimeError('Patch anchor missing: '+a[:100])
 return s.replace(a,b)

def geo_main(s):
 s='#include "surface_detail.hpp"\n'+s
 s=replace(s,'auto o=parse(argc,argv);','auto o=parse(argc,argv);cybr_detail::load_from_environment();')
 s=replace(s,'skyNEE6&&sceneStyle==2','skyNEE6')
 s=replace(s,'CYBR GEO Fernwater R6; local leaf/bark material frames; R5 noise resolve','CYBR SCENES R2 / GEO: stochastic photographic minerals, slope moments, global sky MIS')
 return s
edit('engines/geo/cybr-geo/native/spectral_scenes.cpp',geo_main)

def formation(s):
 s=replace(s,'float lamina=.5f+.5f*std::sin(bed*49.f+.38f*noise(V(p.y*5,p.z*2,0)));','float lamina=.5f+.5f*std::sin(bed*49.f+.38f*noise(V(p.y*5,p.z*2,0)))/(1+sqr(footprint*49.f));')
 s=replace(s,'float crossbed=.5f+.5f*std::sin((bed+.10f*std::sin(p.y*.71f))*113.f+p.y*1.2f);','float crossbed=.5f+.5f*std::sin((bed+.10f*std::sin(p.y*.71f))*113.f+p.y*1.2f)/(1+sqr(footprint*114.f));')
 return s
edit('engines/geo/cybr-geo/native/formation_materials_r2.h',formation)

def geo_material(s):
 s=replace(s,'if(sceneStyle!=2)return shadeLegacyR5(p,n,id,footprint);',r'''if(sceneStyle!=2){
        V gn=n;Surface material=shadeLegacyR5(p,n,id,footprint);
        bool rock=id==1||id==2||id==13;
        if(rock){
            cybr_detail::apply(p,gn,n,material.color,material.rough,footprint,
                sceneStyle==0?.67f:.93f,sceneStyle==0?.56f:.46f,.72f);
            // Salt/rust deposition is spatial, not a repeated bright texture.
            if(sceneStyle==1){float edge=std::exp(-sqr((p.z-.43f)/.19f));
                float algae=edge*smooth(-.12f,.37f,noise(p*9.2f));
                material.color=mixc(material.color,V(.030f,.045f,.020f),algae*.34f);
            }
        }else if(id==0||id==4){cybr_detail::apply(p,gn,n,material.color,material.rough,footprint,1.85f,.15f,.28f);}
        material.color=vmin(vmax(material.color,V(.003f)),V(.88f));
        if(dot(n,gn)<.60f)n=unit(n+gn);
        return material;
    }''')
 # Lower dead-leaf chroma and separate damp decomposed litter from freshly fallen leaves.
 s=replace(s,'mixc(V(.044f,.017f,.005f),V(.235f,.119f,.035f),component)', 'mixc(V(.031f,.022f,.013f),V(.185f,.126f,.069f),component)')
 s=replace(s,'m.rough=dead?.66f:(.38f+.16f*component);','m.rough=dead?(.78f-.27f*wet):(.34f+.23f*component);')
 s=replace(s,'if(dead){float decay=smooth(.20f,.53f,noise(V(u*9,v*6,f->seed)));m.color*=1-.48f*decay;}',r'''if(dead){float decay=smooth(.06f,.48f,noise(V(u*9,v*6,f->seed)));
                m.color=mixc(m.color,V(.020f,.015f,.008f),decay*(.30f+.30f*wet));
            }else{
                // Chlorophyll variation follows each leaf, not world-space tiles.
                float chlorosis=smooth(.26f,.61f,noise(V(u*4.7f,v*3.2f,f->seed)));
                m.color=mixc(m.color,V(.135f,.181f,.036f),chlorosis*.22f);
            }''')
 s=replace(s,'if(grain>0)m.color*=1+grain*', 'if(id==1||id==2||id==5)cybr_detail::apply(p,gn,n,m.color,m.rough,footprint,1.2f,.42f,.60f);\n    if(grain>0)m.color*=1+grain*')
 return s
edit('engines/geo/cybr-geo/native/fernwater_materials_r6.h',geo_material)

def hot_material(s):
 s=replace(s,'Surface m;m.kind=material;','Surface m;m.kind=material;V originalNormal=n;')
 s=replace(s,'m.color*=1-.29f*wet;',r'''// R2: new stochastic photographed microstructure on actual geometry.
 if(material==1||material==2)cybr_detail::apply(p,originalNormal,n,m.color,m.rough,footprint,.86f,.58f,.85f);
 if(material==0||material==4){
  cybr_detail::apply(p,originalNormal,n,m.color,m.rough,footprint,2.7f,.16f,.30f);
  float lamination=std::exp(-sqr((d-.10f)/.28f))*(.45f+.55f*patch);
  float pore=smooth(.10f,.57f,noise(p*53.f))/(1+sqr(footprint*53.f));
  m.color=mixc(m.color,V(.48f,.424f,.283f),lamination*pore*.20f);
 }
 if(dot(n,originalNormal)<.55f)n=unit(n+originalNormal);
 m.color*=1-.29f*wet;''')
 return s
edit('engines/hot/cybr-geo/native/landscape_materials_v11.h',hot_material)

def hot_main(s):
 s='#include "surface_detail.hpp"\n'+s
 s=replace(s,'auto o=parse(argc,argv);','auto o=parse(argc,argv);cybr_detail::load_from_environment();')
 s=replace(s,'float totalPathLength=0;','float totalPathLength=0;bool previousSkyNEE=false;float previousSkyPDF=0;')
 s=replace(s,'scatterWater=waterPool;deltaCount=0;waterReflectionNEE=false;indirect=true;', 'previousSkyNEE=false;scatterWater=waterPool;deltaCount=0;waterReflectionNEE=false;indirect=true;')
 s=replace(s,'scatterWater=-1;deltaCount=0;waterReflectionNEE=false;indirect=true;', 'previousSkyNEE=false;scatterWater=-1;deltaCount=0;waterReflectionNEE=false;indirect=true;')
 s=replace(s,'Spec incoming=physicalSky(ray.d);', 'Spec incoming=physicalSky(ray.d);if(previousSkyNEE&&ray.d.z>0)incoming*=powerWeight(previousSkyPDF,1/(2*PI));')
 s=replace(s,'if(useWater&&(material==6||material==7)){', 'if(useWater&&(material==6||material==7)){previousSkyNEE=false;')
 anchor='Spec base=rgbAnchors(m.color);V v=-ray.d,lAir=sampleSun(rng);'
 s=replace(s,anchor,anchor+r'''
        // Direct sky is sampled separately from the finite solar disc. The
        // BSDF escape path receives the reciprocal MIS weight. Water and leaves
        // are not transparent shortcuts in this environment path class.
        bool sampleSkyHere=waterPool<0&&material!=3&&material!=9;
        if(sampleSkyHere){
            float z=rng.uniform(),phi=2*PI*rng.uniform(),r=std::sqrt(std::max(0.f,1-z*z));V light(r*std::cos(phi),r*std::sin(phi),z);
            float nc=dot(n,light);if(nc>0&&dot(gn,light)>0){Ray shadow(p+gn*EPS*5,light);Hit blocker;
                if(!meshHit(shadow,blocker,true)){float lp=1/(2*PI),bp=pdfBSDF(m,n,v,light),tr=airTransmittance(shadow,INF,rng);
                    recordRadiance(L,throughput*evalBSDF(m,base,n,v,light)*physicalSky(light)*(nc*tr*powerWeight(lp,bp)/lp),indirect);
                }
            }
        }
        previousSkyNEE=false;
''')
 s=replace(s,'scatterWater=waterPool;deltaCount=0;indirect=true;', 'previousSkyNEE=sampleSkyHere;previousSkyPDF=pdf;scatterWater=waterPool;deltaCount=0;indirect=true;')
 s=replace(s,'CYBR GEO native V11 scale-separated microgeometry and jointed ridge terrain','CYBR SCENES R2 / Hot Springs: stochastic sinter/mineral surfaces and sky MIS')
 return s
edit('engines/hot/cybr-geo/native/spectral_desert.cpp',hot_main)

def cave_main(s):
 s='#include "surface_detail.hpp"\n'+s
 s=replace(s,'Surface shade(', 'static inline float r2Smooth(float a,float b,float x){float t=std::min(1.f,std::max(0.f,(x-a)/(b-a)));return t*t*(3-2*t); }\nSurface shade(')
 s=replace(s,'auto o=parse(argc,argv);','auto o=parse(argc,argv);cybr_detail::load_from_environment();')
 s=replace(s,'const auto &tr=tris[hit.tri];const auto &a=attributes[hit.tri];','V originalNormal=n;const auto &tr=tris[hit.tri];const auto &a=attributes[hit.tri];')
 anchor='m.color=vmin(vmax(m.color,V(.002f)),V(.93f));return m;'
 s=replace(s,anchor,r'''if(material==0){
  // Calcite precipitation concentrates along vertical seepage paths. Its
  // wet dielectric response is coupled to the same mask as the deposit.
  float seep=r2Smooth(.12f,.52f,noise(V(p.x*1.8f,p.y*1.8f,p.z*.105f)));
  float deposit=seep*r2Smooth(.9f,5.f,p.z)*.38f;
  m.color=m.color*(1-deposit)+V(.38f,.350f,.290f)*deposit;
  m.rough=m.rough*(1-seep*.35f)+.25f*seep*.35f;
  cybr_detail::apply(p,originalNormal,n,m.color,m.rough,footprint,.86f,.16f,.38f);
 }
 if(material==1||material==2)cybr_detail::apply(p,originalNormal,n,m.color,m.rough,footprint,1.7f,.18f,.40f);
 if(dot(n,originalNormal)<.55f)n=unit(n+originalNormal);
 m.color=vmin(vmax(m.color,V(.002f)),V(.88f));return m;''')
 s=replace(s,'float alpha=(mat==8?.022f:.042f)*(1+.22f*noise(p*8.f));',r'''// Clear exposed tips and rough weathered attachment zones. All sampling,
   // BSDF evaluation and PDFs below receive this identical alpha.
   float clearTip=r2Smooth(.22f,1.6f,p.z);
   float etch=r2Smooth(.18f,.58f,noise(p*5.1f));
   float alpha=(mat==8?.013f:.029f)+.026f*(1-clearTip)+.012f*etch;
''')
 s=replace(s,'CYBR GEO native cavern V3 - rough-quartz NEE spectral CPU','CYBR SCENES R2 / Drowned Geode: seepage mineral layers and weathered quartz')
 return s
edit('engines/geode/src/cathedral_v3.cpp',cave_main)

# Preserve a machine-readable patch ledger and ordinary unified diffs.
(ROOT/'provenance/renderer-changes.json').write_text(json.dumps(changes,indent=2)+'\n')
patch=[]
for entry in changes:
 p=ROOT/entry['file'];old=(ROOT/'provenance/native-before'/entry['file']).read_text()
 patch.extend(difflib.unified_diff(old.splitlines(True),p.read_text().splitlines(True),fromfile='a/'+entry['file'],tofile='b/'+entry['file']))
(ROOT/'provenance/renderer-upgrade.diff').write_text(''.join(patch))
print(json.dumps(changes,indent=2))
