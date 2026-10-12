"""Stable execution-record paths, independent of shared job basenames."""
import hashlib
from pathlib import Path


def execution_paths(job_path, receipt_root):
    """Name records by stem plus resolved-path hash; image paths are untouched."""
    job_path = Path(job_path).resolve()
    suffix = hashlib.sha256(str(job_path).encode('utf-8')).hexdigest()[:16]
    key = job_path.stem + '_' + suffix
    root = Path(receipt_root)
    return {
        'log': root / (key + '.log'),
        'performance': root / (key + '_performance.json'),
        'cleanup': root / (key + '_cleanup.json'),
    }
