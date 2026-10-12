# Source ownership, attribution and limits

## Geographic sources

- UC Santa Barbara campus GIS supplies mapped buildings, paths, driving surfaces,
  lawns, tree roots/genus and the complete lagoon outline. `INPUTS.json` records
  exact public query URLs and historical hashes. The inspected ArcGIS item and
  service metadata did not specify a redistribution license. Raw UCSB responses
  are therefore omitted from this repository and fetched directly by the consumer.
  Public service access is not described as an open redistribution grant.
- The two retained elevation exports are USGS 3DEP public-domain data. They are
  floating-point height rasters, not imagery. Their export spacing is about 2.54 m;
  that is not a claim of native source accuracy. Their datum and hydroflattened
  water surface remain the provider's, not a current water-level measurement.
- `SOURCE_COVERAGE.geojson` is an OSM-derived geographic database under ODbL 1.0,
  © OpenStreetMap contributors, https://www.openstreetmap.org/copyright and
  https://opendatacommons.org/licenses/odbl/1-0/ . The file retains source IDs,
  source element versions/timestamps and geographic ring geometry projected into
  the documented local UTM frame. It is supplied in editable form under that
  same database license. Code license does not supersede its ODbL terms.

## Photographic and descriptive references

The Cheadle Center's San Nicolas restoration photograph, official restoration
history, 2012 walking tour and UCSB housing descriptions are linked in
`references/recovered-san-nicolas/REFERENCES.json`. Photograph and PDF pixels are
not redistributed and are never used as textures. Basin outline/elevation,
architectural section splits, individual plant locations/morphology and optical
weather state are explicit reconstruction estimates, not source measurements.

## Original procedural dependencies

The scene uses original CYBR coordinate, meshlet, polygon and facade construction.
Exact helper extraction provenance is in `SCENE_SOURCE.json`. LIGHT transport is
provided by the separately installed `cybrlight.scene_compat` package, with its
GPL 2 and retained original MIT notices; no C++ renderer is duplicated here.

Original material field recipes are fetched from the pinned CYBR MATERIAL commit
12848c82f60bc58fa88640545868009b90298b32 and hash-checked. Coastal pigments, linked
roughness and radiance controls are authored scene adaptations. This is not a
new catalogue recipe or a claim of parity with a selected Blender material slab.

The clear-sky input is a retained numerical Nishita radiance export, with its
source/compiler provenance in `evidence/coherent-daylight`. It is mixed with a
CIE-overcast angular model in source. There are no photographic sky textures,
reference-image projections, image-generation outputs or per-image color grades.

## Standard observer data

`work/cybr-light/data/CIE_xyz_1931_2deg.csv` is the unmodified CIE 1931 two-degree
color-matching-function dataset. Credit: CIE (2019), CIE 1931 colour-matching
functions, 2 degree observer, DOI https://doi.org/10.25039/CIE.DS.xvudnb9b .
Official dataset: https://cie.co.at/datatable/cie-1931-colour-matching-functions-2-degree-observer . It is provided
under Creative Commons Attribution-ShareAlike 4.0 International:
https://creativecommons.org/licenses/by-sa/4.0/ . No data values were changed.
The verified official file MD5 is 17cca777db64b17170f06f67ce9d3ab7; source metadata
and the license record are retained in the verification evidence.
