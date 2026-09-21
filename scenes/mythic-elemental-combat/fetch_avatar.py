#!/usr/bin/env python3
"""Fetch the permissively redistributable rig used by the combat demo."""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/CesiumMan/glTF-Binary/CesiumMan.glb"
SOURCE = "KhronosGroup/glTF-Sample-Assets / Models/CesiumMan"
LICENSE = "Creative Commons Attribution 4.0 International (CC BY 4.0)"
CREDIT = "Cesium, 2017"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "assets" / "CesiumMan.glb")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists() and not args.force:
        payload = args.out.read_bytes()
    else:
        req = urllib.request.Request(URL, headers={"User-Agent": "CYBR-SCENES/1.0"})
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = response.read()
        if len(payload) < 1024 or payload[:4] != b"glTF":
            raise RuntimeError("Downloaded asset is not a valid binary glTF")
        args.out.write_bytes(payload)
    receipt = {
        "source": SOURCE,
        "url": URL,
        "license": LICENSE,
        "credit": CREDIT,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }
    (args.out.parent / "CesiumMan.provenance.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
