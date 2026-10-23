"""Source locations shared by the recovered geo/hot build and receipt tools.

Only the six consolidated implementations are redirected. A missing shared file
is an error: an engine-local legacy copy must never silently replace its owner.
"""
from pathlib import Path

SHARED_DIRECTORY = Path(__file__).resolve().parent / 'shared'
SHARED_HEADERS = frozenset({
    'cloud_volume_v9.h', 'granular_relief_v11.h', 'photographic_grain.h',
    'single_scatter_sky.h', 'spectral_geometry.h', 'steam_volume_v11.h',
})


def native_source(native: Path, name: str) -> Path:
    """Resolve an existing logical source name without changing hash order."""
    return (SHARED_DIRECTORY if name in SHARED_HEADERS else native) / name


def shared_include_flags() -> list[str]:
    return ['-I', str(SHARED_DIRECTORY)]


def dependency_files(native: Path, entrypoint: str) -> list[Path]:
    """Include shared bodies in source-sensitive executable reuse decisions."""
    return sorted({native / entrypoint,
                   *native.glob('*.h'), *native.glob('*.hpp'),
                   *SHARED_DIRECTORY.glob('*.h'), *SHARED_DIRECTORY.glob('*.hpp')})
