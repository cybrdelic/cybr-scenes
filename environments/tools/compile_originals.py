#!/usr/bin/env python3
"""Reconstruct and compile the pre-upgrade native code without touching R2.

Unchanged headers come from engines/. Every edited source/header is overlaid from
provenance/native-before/. This avoids accidentally comparing R2 with itself.
"""
from pathlib import Path
import sys,shutil,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cybr_scenes import SOURCES,run,sha,atomic_json,dependency_fingerprint

def main():
 work=ROOT/'build/original-engines';work.mkdir(parents=True,exist_ok=True)
 for engine,source in SOURCES.items():
  target=work/engine;target.mkdir(parents=True,exist_ok=True)
  for path in (ROOT/'engines'/engine).rglob('*'):
   if path.is_file() and path.suffix in ['.cpp','.hpp','.h','.inl','.inc']:
    relative=path.relative_to(ROOT);backup=ROOT/'provenance/native-before'/relative
    dst=target/path.relative_to(ROOT/'engines'/engine);dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(backup if backup.exists() else path,dst)
  compiler=shutil.which('g++')
  if not compiler:raise RuntimeError('g++ is required')
  binary=ROOT/'build'/f'{engine}_original'
  cmd=[compiler,'-std=c++17','-O3','-march=native','-fno-math-errno','-fopenmp']
  if engine=='obsidian':cmd+=['-I'+str(work/'obsidian/include')]
  if engine=='geode':cmd+=['-mavx2','-ffp-contract=off']
  cmd+=[str(work/Path(source).relative_to('engines')),'-o',str(binary)]
  result=run(cmd,ROOT,ROOT/'evidence'/f'compile-original-{engine}.log')
  result.update(executable_sha256=sha(binary),source_fingerprint=dependency_fingerprint(engine,original=True))
  atomic_json(binary.with_suffix('.build.json'),result)
  if engine!='obsidian':run([binary,'--self-test'],ROOT,ROOT/'evidence'/f'original-self-test-{engine}.log')
if __name__=='__main__':main()
