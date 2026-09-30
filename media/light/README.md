# Fresh CYBR LIGHT preview

[Quiet Observatory IV](observatory_hero.png) was traced from its actual 1.51-million
triangle scene at 800 × 533, with 96 sample packets × 8 wavelengths per pixel.
The display image uses three camera-footprint, geometry, component and variance
guided filtering passes, then ACES. The original linear PFM/EXR films are unchanged.
No image-generation step or photographic backplate was used.

[Unfiltered image](observatory_hero_unfiltered.png) ·
[Native metadata, command and file hashes](renders.json).

```bash
python cybr_scenes.py render observatory-iv --quality preview --width 800 --spp 96 --threads 6 --output outputs/light-final
```

This is a finite-sample preview, with remaining Monte Carlo noise and clipped
daylight highlights. The root workflow writes its receipt after checking native
film finiteness, dimensions and invalid-path counts. Geometry/material and output
hashes govern reuse. The retained environment gallery has its original renderer
provenance; these new renders have separate records.
