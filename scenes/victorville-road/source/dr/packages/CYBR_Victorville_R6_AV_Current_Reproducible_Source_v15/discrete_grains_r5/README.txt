VICTORVILLE GROUND R5D — PROCEDURAL WORK IN PROGRESS

Status: improved construction prototype, not a finished photoreal material or exact site reconstruction. Coarse fracture faces remain overly clean. This checkpoint is not a selected catalogue material.

All material content is generated from code. Public NPS photographs were observed only, never used as textures or scans. No image generation was used.

Units: metres. Ground extent 0.18 m. 73,733 separate sand/grit/fragment bodies, with diameter bands 0.16–0.64 mm, 0.6–1.9 mm and 1.6–5.8 mm. The fines bed has about 0.538 mm nominal cell pitch and up to 99 micrometres relief before spatial compaction modulation. Geometric particles have oblique fracture planes, narrow edge truncations, partial burial, per-particle mineral color/roughness and restrained intragrain variation.

Ground reconstruction (Python 3 with numpy/scipy, Blender 4.3.2):
  python src/fracture_prototypes.py
  python src/compacted_microbed.py
  blender -b -t 2 --python-exit-code 1 --python src/build_diagnostic.py
This creates preview/diagnostic_d.blend. Open it to render, or use the included guided capture pipeline.

Edge context additionally needs the original dense asphalt fields. They can be regenerated from the retained exact construction source:
  OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 python asphalt/source/generate_native4096.py
  blender -b -t 2 --python-exit-code 1 --python src/build_edge_context.py
The original native4096 asphalt evaluation is approximately a 4 GiB operation. Do not run it concurrently with Blender on a small host. Asphalt is the original dense packed-grain model shown in the liked comparison, not the later fracture/plate revision.

The edge scene uses a real ragged asphalt boundary, 629 selected fine-grain bodies on the pavement, and a narrow shelter-linked dust coating. It has no raised dust ribbon and no broad normal/height material blend.

Reconstruction programs save scenes without rendering. A JSON job for pipeline/clean_render.sh requires source path/hash, output path, engine CYCLES, width/height, samples, capture_mode guided, save_guides true, and CPU resource limits. Set OIDN_BIN to an installed official OIDN 2.5.1 oidnDenoise binary; it is not bundled. The supplied captures used CPU 2 threads, 48 samples, guided OIDN, AgX Medium High Contrast, and analytic daylight.

Current review images are separate Library files. Large generated scenes/maps and copyrighted reference photographs are intentionally absent from this small source archive. R4 comparison uses the preserved rejected source; its image is not a same-particle A/B test.
