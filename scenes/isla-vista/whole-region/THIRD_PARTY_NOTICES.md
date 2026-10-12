# Dataset and source notices

The repository's GPL-2.0-only code license does not replace dataset licenses,
provider conditions, photographic copyright or geographic uncertainty.

## OpenStreetMap

© OpenStreetMap contributors. The nine dated XML snapshots and OSM-derived
database portions are made available under the Open Database License 1.0.
Retain this credit and the applicable attribution/share-alike requirements
when distributing adapted databases or produced works. Original authored
reconstruction parameters are identified separately from source map records.

- https://www.openstreetmap.org/copyright
- https://opendatacommons.org/licenses/odbl/1-0/

## UCSB campus GIS

Credit UC Santa Barbara and the source services named in `INPUTS.json` and the
geographic manifests. The acquired service metadata did not establish an
explicit redistribution license. Raw campus pages are therefore obtained
directly by the user through the checked public downloader, rather than
redistributed in this repository. No survey-grade or current-condition claim
follows from their use. Provider schema changes are not treated as geometry
changes, but the entire consumed ordered-feature contract is checked.

## USGS, NOAA and Census

Credit USGS 3DEP for the geographic elevation exports. Credit the USGS CoNED
project, Tyler and Danielson, NOAA Office for Coastal Management, and the
original survey contributors for the Southern California topobathymetric
model. Its compiled 2016 product uses observations from 1930–2014; local source
dates and quality vary. The provider lists no access restrictions, warns of
temporal change and disclaims suitability for critical use without awareness
of limitations. NAVD88 elevations are retained without an invented tidal
conversion. The horizontal operation's stated 4 m accuracy is separate from
the native 1 m raster spacing.

- https://www.fisheries.noaa.gov/inport/item/55359
- https://doi.org/10.5066/P9UZIYI8

Credit the U.S. Census Bureau TIGERweb for the IV Census-designated-place and
2010/2020 urban-area boundaries. These geographic boundary extracts are U.S.
government data; the original source URLs/receipts accompany them.

## Dated California classifications

The CDFW archive is fetched from its official public source. Cite California
Department of Fish and Wildlife for contract/database management and Sandoval
& Associates LLC for data collection and processing. Preserve the original
metadata and its conditions. September 2016 classified canopy polygons are
not individual fronds, present-day coverage or measured local optical data.
The source's general ownership policy distinguishes state information from
third-party material; no additional copyright license is invented here.

- https://filelib.wildlife.ca.gov/Public/R7_MR/BIOLOGICAL/Kelp/BIO_CA_Kelp2016.zip
- https://wildlife.ca.gov/Conditions-of-Use

Credit CAL FIRE Urban and Community Forestry, USDA Forest Service, NOAA and
EarthDefine for the 2022 urban-canopy classification, released May 2025.
The local raster is an aligned native window, not a photographic texture or
an individual-tree inventory. Native 0.6 m cell spacing does not imply 0.6 m
positional accuracy. The provider disclaims accuracy warranties and liability;
CAL FIRE's GIS conditions require attribution and identifying modifications.
The public source archive is fetched directly, preserving its own metadata.

- https://www.fire.ca.gov/what-we-do/fire-resource-assessment-program/gis-mapping-and-data-analytics
- https://www.fire.ca.gov/conditions-of-use/
- https://urban-and-community-forestry-calfire-forestry.hub.arcgis.com/

## Reference photographs and original software

Property-manager, UCSB/Pardall and CCBER photographs are cited only as links,
checksums and original observations. Their pixels are not bundled, projected
or used as material textures. Copyright remains with the source holders.
Unknown dates, unresolved property-view assignment and authored estimates
remain explicit in the reference manifests and per-building receipts.

Original CYBR GEO/TERRAIN and MATERIAL software retain the pinned repository
ownership and GPL source license. The reviewed LIGHT namespace snapshot has
its own complete license/notice files in the parent scene's vendor directory.
The single procedural sky radiance field is accompanied by its original
Blender Nishita export and colorimetric-fit source and provenance; no generated
photographic model is involved.
