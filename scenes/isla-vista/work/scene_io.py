"""Retained finite floating-point PFM writer; no image synthesis."""
from pathlib import Path
import numpy as np

def write_pfm(path,array):
    a=np.asarray(array,dtype='<f4')
    if a.ndim!=3 or a.shape[2]!=3 or not np.isfinite(a).all():raise ValueError("Invalid texture")
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('wb') as stream:
        stream.write(f'PF\n{a.shape[1]} {a.shape[0]}\n-1.0\n'.encode());stream.write(a[::-1].tobytes())
    return path
