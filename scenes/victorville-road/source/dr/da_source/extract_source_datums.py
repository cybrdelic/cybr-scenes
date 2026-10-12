"""Re-evaluate pinned R5D packing and RNG stream; retain exact source sand/chip/grit datum witnesses."""
from pathlib import Path
import argparse,ast,hashlib,json,math,time
import numpy as np

def build(builder,fractures,out):
 raw=Path(builder).read_bytes();assert hashlib.sha256(raw).hexdigest()=='320dd02e5ac661f4f9f3b470d614e0b3fb103614b0d2cd740aded5964ffa4246'
 tree=ast.parse(raw);env={'np':np,'math':math,'rng':np.random.default_rng(501809),'side':.18}
 funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('noise','deposit','ground')]
 exec(compile(ast.Module(body=funcs,type_ignores=[]),'<original-functions>','exec'),env)
 txt=raw.decode();packing=txt.split('cell=.00009;',1)[1].split('# Bounded angular chips',1)[0]
 exec('cell=.00009;'+packing,env)
 assert [row[1] for row in env['counts']]==[297,8859,64577]
 env.update(verts=[],faces=[],colors=[],roughness=[],particle_ids=[],palette=np.array([[.56,.53,.45],[.39,.315,.225],[.265,.205,.135],[.145,.163,.154],[.49,.385,.26],[.165,.108,.062],[.34,.34,.31]]),prototypes=json.loads(Path(fractures).read_text()),selected=set(np.linspace(9156,73732,64,dtype=int).tolist()) | set((13, 23, 26, 32, 35, 36, 50, 52, 61, 62, 63, 64, 70, 78, 79, 83, 88, 90, 93, 98, 108, 116, 117, 129, 136, 143, 149, 151, 167, 168, 172, 179, 199, 206, 210, 211, 222, 226, 230, 247, 250, 256, 261, 265, 266, 273, 278, 292, 328, 784, 2934, 3077, 3821, 4243, 4744, 4975, 5933, 6351, 6454, 7589, 7649, 8453, 9012, 9033)),saved=[])
 loop=next(n for n in tree.body if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple) and isinstance(n.target.elts[0],ast.Name) and n.target.elts[0].id=='particle_id')
 # Only remove pure output-list operations, leaving ALL random draws unchanged.
 class StripOutput(ast.NodeTransformer):
  def visit_Expr(self,n):
   if isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name) and n.value.func.value.id in {'verts','faces','colors','roughness','particle_ids'}:return None
   return self.generic_visit(n)
 loop=StripOutput().visit(loop)
 extra=ast.parse("""
if particle_id in selected:
 saved.append(dict(source_id=particle_id,vertices=(local-np.array([x,y,float(ground(x,y))])).tolist(),faces=fs,colors=cc.tolist(),roughness=rr.tolist(),nominal_diameter_m=d,original_xy_m=[x,y],original_deposit=dep))
""").body
 loop.body.extend(extra);exec(compile(ast.fix_missing_locations(ast.Module(body=[loop],type_ignores=[])),'<original-particle-loop>','exec'),env)
 assert len(env['saved'])==128
 report=dict(builder_sha256=hashlib.sha256(raw).hexdigest(),fractures_sha256=hashlib.sha256(Path(fractures).read_bytes()).hexdigest(),counts=env['counts'],occupied_mask_fraction=float(env['occ'].mean()),recipe='Exact original RNG, packing, shape and per-vertex material; source particle ids selected after full stream, geometry centred at source support datum',particles=env['saved'])
 Path(out).write_text(json.dumps(report,separators=(',',':'))+'\n');print('SAND_BANK',len(env['saved']),Path(out).stat().st_size,flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('builder');p.add_argument('fractures');p.add_argument('out');a=p.parse_args();build(a.builder,a.fractures,a.out)
