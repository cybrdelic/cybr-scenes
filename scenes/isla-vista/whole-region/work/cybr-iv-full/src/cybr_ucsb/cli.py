"""Reproducible acquisition, geometry, native rendering and media commands."""
from pathlib import Path
import argparse
import json
from .coordinates import Sector
from .sources import acquire, Archive, write_json, sha256


def main(argv=None):
    parser = argparse.ArgumentParser(description="CYBR UCSB geospatial reconstruction")
    parser.add_argument("--data",default="data/raw")
    parser.add_argument("--output",default="outputs/sector01")
    parser.add_argument("--longitude",type=float,default=-119.855)
    parser.add_argument("--latitude",type=float,default=34.4135)
    parser.add_argument("--extent",type=float,default=2048.0)
    commands = parser.add_subparsers(dest="command",required=True)
    commands.add_parser("acquire",help="Fetch real GIS, OSM and float32 USGS elevation")
    commands.add_parser("ingest",help="Verify inputs and normalize to local UTM metres")
    p = commands.add_parser("build",help="Generate a source-anchored CYBR GEO model")
    p.add_argument("--grid",type=int,default=257)
    p = commands.add_parser("render",help="Trace native CYBR LIGHT stills")
    p.add_argument("--view",choices=["overview","north-up","campus","isla-vista"],default="overview")
    p.add_argument("--width",type=int,default=1280)
    p.add_argument("--height",type=int,default=800)
    p.add_argument("--spp",type=int,default=64)
    p.add_argument("--threads",type=int,default=8)
    p.add_argument("--bands",type=int,default=8)
    p = commands.add_parser("film",help="Trace every moving-camera frame, then encode H.264")
    p.add_argument("--frames",type=int,default=48)
    p.add_argument("--fps",type=int,default=12)
    p.add_argument("--width",type=int,default=640)
    p.add_argument("--height",type=int,default=400)
    p.add_argument("--spp",type=int,default=12)
    p.add_argument("--threads",type=int,default=8)
    p.add_argument("--bands",type=int,default=4)
    commands.add_parser("validate",help="Source hashes, geographic/geometry regressions, render and media receipts")
    args = parser.parse_args(argv)
    data,output = Path(args.data),Path(args.output)
    sector = Sector(longitude=args.longitude,latitude=args.latitude,extent=args.extent)
    if args.command=="acquire":
        acquire(data,sector)
    elif args.command in ("ingest","build"):
        from .ingest import ingest
        dataset = ingest(data,sector)
        if args.command=="ingest":
            dataset.save(output/"normalized.geojson")
            write_json(output/"ingestion.json",dataset.report)
            print(json.dumps(dataset.report["counts"],indent=2))
        else:
            from .geometry import build
            build(dataset,output,args.grid)
    elif args.command=="render":
        from .rendering import render_view
        render_view(output,args.view,args.width,args.height,args.spp,args.threads,args.bands)
    elif args.command=="film":
        from .rendering import film
        film(output,output/"sector01-orbit.mp4",args.frames,args.fps,args.width,args.height,args.spp,args.threads,args.bands)
    elif args.command=="validate":
        from .validation import validate
        print(json.dumps(validate(data,output,sector),indent=2))
