"""Regress real source coordinates, exported massing and actual native films."""
from pathlib import Path
import json
import subprocess
import numpy as np
from PIL import Image
from cybr_light.runtime import read_pfm
from .ingest import ingest
from .sources import Archive, write_json, sha256
from .coordinates import Sector


def validate(data,output,sector=Sector()):
    output = Path(output)
    dataset = ingest(data,sector)
    report = {"schema":"cybr-ucsb-validation/1","checks":[],"image_generation_used":False}
    def check(name,passed,details):
        if not bool(passed):
            raise ValueError(f"Regression failed: {name}: {details}")
        report["checks"].append({"name":name,"passed":True,"details":details})
    ids = [f.id for f in dataset.features]
    check("source IDs unique",len(ids)==len(set(ids)),len(ids))
    check("source response hashes",Archive(data).verify()>0,Archive(data).verify())
    frame = dataset.sector.frame
    lons = np.array([-119.865,-119.855,-119.845,-119.848396])
    lats = np.array([34.408,34.4135,34.419,34.412640])
    xy = frame.local(lons,lats)
    back = frame.geographic(*xy)
    error = np.max(np.abs(np.c_[back[0]-lons,back[1]-lats]))
    check("longitude/latitude round trip",error<1e-10,{"maximum_error_degrees":float(error)})
    tower = next(f for f in dataset.selected("building") if f.properties.get("name")=="Storke Tower")
    from shapely.geometry import Point
    point = Point(*frame.local(-119.848396,34.412640))
    distance = tower.geometry.distance(point)
    check("official Storke anchor",distance<15,{"distance_to_footprint_m":distance})
    check("published Storke height",abs(tower.properties["height_m"]-53.34)<1e-9,tower.properties["height_m"])
    from .geometry import ocean_from_coastline
    ocean = ocean_from_coastline(dataset)
    offshore = Point(*frame.local(-119.859,34.405))
    inland = Point(*frame.local(-119.859,34.412))
    check("real coast separates ocean and Isla Vista",ocean.covers(offshore) and not ocean.covers(inland),
          {"ocean_area_m2":ocean.area,"offshore":True,"inland":False})
    for feature in dataset.selected("building"):
        if feature.properties.get("name")=="Storke Publications":
            check("GIS tower-height conflict isolated",feature.properties["height_m"]<30,
                  {"raw_GIS_height":feature.properties.get("BLDGHEIGHT"),"massing_height_m":feature.properties["height_m"]})
    check("measured terrain finite and coastal",np.isfinite(dataset.dem.values).all() and dataset.dem.values.max()<100,
          {"minimum_m":float(dataset.dem.values.min()),"maximum_m":float(dataset.dem.values.max())})
    if (output/"geometry-provenance.json").exists():
        geometry = json.loads((output/"geometry-provenance.json").read_text())
        max_area_error = max(row["error_m2"] for row in geometry["footprint_area_regressions"])
        check("all exported footprint/roof areas",max_area_error<1e-5,
              {"count":len(geometry["footprint_area_regressions"]),"maximum_error_m2":max_area_error})
        check("TERRAIN source elevation retained",geometry["terrain_height_max_error_m"]<1e-10,
              geometry["terrain_height_max_error_m"])
        check("GEO geometry exported",(output/"sector.glb").is_file(),geometry.get("glb_sha256"))
        if geometry.get("glb_sha256"):
            check("GLB hash retained",sha256(output/"sector.glb")==geometry["glb_sha256"],geometry["glb_sha256"])
    native = output/"native-assets.json"
    if native.exists():
        assets = json.loads(native.read_text())
        check("native meshlet hash",sha256(output/"sector.clm")==assets["meshlets_sha256"],assets["triangles"])
    if (output/"north-up_position.pfm").exists():
        positions = read_pfm(output/"north-up_position.pfm")
        objects = read_pfm(output/"north-up_object.pfm")[:,:,0]
        height,width = positions.shape[:2]
        scale = 2200.
        # An orthographic top-down ray has a known metric pixel footprint.
        # Verify the actual renderer axis bridge using a known source landmark.
        x,y = frame.local(-119.848396,34.412640)
        col = int(round((float(x)/(scale*width/height)+.5)*width-.5))
        row = int(round((.5-float(y)/scale)*height-.5))
        actual = positions[row,col]
        check("native north-up metric/axis bridge",np.linalg.norm(actual[:2]-[x,y])<scale/height*1.5,
              {"known_anchor_local_m":[float(x),float(y)],"rendered_position_m":actual.tolist(),"pixel":[col,row]})
        layout = json.loads((output/"glb-part-layout.json").read_text())
        lookup = {span["component"]:span["part"] for group in layout.values() for span in group["parts"]}
        for lon,lat,water_expected in [(-119.859,34.405,True),(-119.859,34.412,False)]:
            xx,yy = frame.local(lon,lat)
            cc = int(round((float(xx)/(scale*width/height)+.5)*width-.5))
            rr = int(round((.5-float(yy)/scale)*height-.5))
            part = lookup.get(int(round(float(objects[rr,cc]))),"")
            check("rendered coast classification "+str((lon,lat)),
                  part.startswith("source_water_")==water_expected,{"part":part,"water_expected":water_expected})
    films = []
    for path in sorted(output.glob("*.json")):
        d = json.loads(path.read_text())
        if "engine_source_sha256" not in d:
            continue
        stem = path.with_suffix("")
        if not stem.with_suffix(".png").exists():
            continue
        linear = read_pfm(stem.with_suffix(".pfm"))
        size = Image.open(stem.with_suffix(".png")).size
        check("native film "+stem.name,np.isfinite(linear).all() and float(linear.max())>0 and not d.get("invalid_path_samples",0),
              {"shape":list(linear.shape),"display_size":list(size),"engine_sha256":d["engine_source_sha256"]})
        check("display/film dimensions "+stem.name,tuple(linear.shape[:2][::-1])==size,size)
        for name,digest in d.get("output_hashes",{}).items():
            check("render asset "+name,sha256(output/name)==digest,digest)
        films.append(stem.name)
    report["rendered_views"] = films
    for path in output.glob("*.mp4"):
        subprocess.run(["ffmpeg","-v","error","-xerror","-i",str(path),"-f","null","-"],check=True)
        record = json.loads(path.with_suffix(".json").read_text())
        check("decoded video "+path.name,sha256(path)==record["video_sha256"],record["probe"])
    report["passed"] = True
    report["geographic_claim"] = "Coordinates/topology are sourced; source errors, time differences and missing dimensions remain explicit"
    write_json(output/"validation.json",report)
    return report
