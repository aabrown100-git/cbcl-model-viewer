from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pyvista as pv


@dataclass(frozen=True)
class CacheRecord:
    source: str
    source_mtime_ns: int
    source_size: int


class SurfaceCache:
    """Create lightweight PyVista surface files for VTK visualization sources."""

    def __init__(self, cache_root: str | Path):
        self.cache_root = Path(cache_root).expanduser().resolve()

    def surface_for(
        self,
        source: str | Path,
        *,
        model_id: str,
        part_id: str,
        timestep_index: int,
    ) -> Path:
        source_path = Path(source).expanduser().resolve()
        output_path = self._surface_path(source_path, model_id, part_id, timestep_index)
        record_path = output_path.with_suffix(".json")
        record = self._record_for(source_path)

        if output_path.exists() and record_path.exists():
            try:
                cached = CacheRecord(**json.loads(record_path.read_text()))
            except (TypeError, json.JSONDecodeError):
                cached = None
            if cached == record:
                return output_path

        output_path.parent.mkdir(parents=True, exist_ok=True)
        mesh = pv.read(source_path)
        surface = mesh if isinstance(mesh, pv.PolyData) else mesh.extract_surface(algorithm="dataset_surface")
        surface.save(output_path)
        record_path.write_text(json.dumps(record.__dict__, indent=2) + "\n")
        return output_path

    def _surface_path(self, source: Path, model_id: str, part_id: str, timestep_index: int) -> Path:
        safe_stem = source.stem.replace(" ", "-")
        return (
            self.cache_root
            / model_id
            / part_id
            / f"{timestep_index:04d}-{safe_stem}-surface.vtp"
        )

    @staticmethod
    def _record_for(source: Path) -> CacheRecord:
        stat = source.stat()
        return CacheRecord(
            source=str(source),
            source_mtime_ns=stat.st_mtime_ns,
            source_size=stat.st_size,
        )
