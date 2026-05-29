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

    def glyphs_for(
        self,
        source: str | Path,
        *,
        model_id: str,
        part_id: str,
        timestep_index: int,
        preset_id: str,
        vectors: str,
        scale_factor: float,
        glyph_count: int,
    ) -> Path:
        source_path = Path(source).expanduser().resolve()
        output_path = self._analysis_path(
            source_path,
            model_id=model_id,
            part_id=part_id,
            timestep_index=timestep_index,
            preset_id=preset_id,
            kind="glyphs",
        )
        payload = {
            "vectors": vectors,
            "scale_factor": round(scale_factor, 6),
            "glyph_count": int(glyph_count),
        }
        return self._derived_polydata_for(
            source_path,
            output_path,
            parameters=payload,
            builder=lambda mesh: self._build_glyphs(
                mesh,
                vectors=vectors,
                scale_factor=scale_factor,
                glyph_count=glyph_count,
            ),
        )

    def streamlines_for(
        self,
        source: str | Path,
        *,
        model_id: str,
        part_id: str,
        timestep_index: int,
        preset_id: str,
        vectors: str,
        seed_center: tuple[float, float, float],
        seed_radius: float,
        seed_points: int,
        tube_radius: float,
    ) -> Path:
        source_path = Path(source).expanduser().resolve()
        output_path = self._analysis_path(
            source_path,
            model_id=model_id,
            part_id=part_id,
            timestep_index=timestep_index,
            preset_id=preset_id,
            kind="streamlines",
        )
        payload = {
            "vectors": vectors,
            "seed_center": list(seed_center),
            "seed_radius": round(seed_radius, 6),
            "seed_points": int(seed_points),
            "tube_radius": round(tube_radius, 6),
        }
        return self._derived_polydata_for(
            source_path,
            output_path,
            parameters=payload,
            builder=lambda mesh: self._build_streamlines(
                mesh,
                vectors=vectors,
                seed_center=seed_center,
                seed_radius=seed_radius,
                seed_points=seed_points,
                tube_radius=tube_radius,
            ),
        )

    def _surface_path(self, source: Path, model_id: str, part_id: str, timestep_index: int) -> Path:
        safe_stem = source.stem.replace(" ", "-")
        return (
            self.cache_root
            / model_id
            / part_id
            / f"{timestep_index:04d}-{safe_stem}-surface.vtp"
        )

    def _analysis_path(
        self,
        source: Path,
        *,
        model_id: str,
        part_id: str,
        timestep_index: int,
        preset_id: str,
        kind: str,
    ) -> Path:
        safe_stem = source.stem.replace(" ", "-")
        return (
            self.cache_root
            / model_id
            / part_id
            / "analysis"
            / f"{timestep_index:04d}-{safe_stem}-{preset_id}-{kind}.vtp"
        )

    def _derived_polydata_for(
        self,
        source_path: Path,
        output_path: Path,
        *,
        parameters: dict[str, object],
        builder,
    ) -> Path:
        record_path = output_path.with_suffix(".json")
        record = {
            **self._record_for(source_path).__dict__,
            "parameters": parameters,
        }

        if output_path.exists() and record_path.exists():
            try:
                cached = json.loads(record_path.read_text())
            except json.JSONDecodeError:
                cached = None
            if cached == record:
                return output_path

        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = builder(pv.read(source_path))
        if result.n_points == 0:
            result = pv.PolyData()
        result.save(output_path)
        record_path.write_text(json.dumps(record, indent=2) + "\n")
        return output_path

    @staticmethod
    def _build_glyphs(
        mesh: pv.DataSet,
        *,
        vectors: str,
        scale_factor: float,
        glyph_count: int,
    ) -> pv.PolyData:
        source = mesh.cell_data_to_point_data() if mesh.cell_data.keys() else mesh
        source = _dataset_with_point_array(source, vectors)
        source = _subsample_points(source, glyph_count)
        magnitude_name = f"{vectors}_magnitude"
        source.point_data[magnitude_name] = _vector_magnitudes(source.point_data[vectors])
        glyphs = source.glyph(
            orient=vectors,
            scale=magnitude_name,
            factor=scale_factor,
            geom=pv.Arrow(),
        )
        return glyphs if isinstance(glyphs, pv.PolyData) else glyphs.extract_surface()

    @staticmethod
    def _build_streamlines(
        mesh: pv.DataSet,
        *,
        vectors: str,
        seed_center: tuple[float, float, float],
        seed_radius: float,
        seed_points: int,
        tube_radius: float,
    ) -> pv.PolyData:
        source = _dataset_with_point_array(mesh, vectors)
        streamlines = source.streamlines(
            vectors=vectors,
            source_center=seed_center,
            source_radius=seed_radius,
            n_points=seed_points,
            progress_bar=False,
        )
        if tube_radius > 0 and streamlines.n_points:
            streamlines = streamlines.tube(radius=tube_radius)
        return streamlines if isinstance(streamlines, pv.PolyData) else streamlines.extract_surface()

    @staticmethod
    def _record_for(source: Path) -> CacheRecord:
        stat = source.stat()
        return CacheRecord(
            source=str(source),
            source_mtime_ns=stat.st_mtime_ns,
            source_size=stat.st_size,
        )


def _dataset_with_point_array(mesh: pv.DataSet, array_name: str) -> pv.DataSet:
    if array_name in mesh.point_data:
        return mesh
    if array_name in mesh.cell_data:
        return mesh.cell_data_to_point_data()

    available = sorted({*mesh.point_data.keys(), *mesh.cell_data.keys()})
    raise ValueError(f"Array '{array_name}' was not found. Available arrays: {available}")


def _subsample_points(mesh: pv.DataSet, glyph_count: int) -> pv.PolyData:
    points = _point_cloud(mesh)
    total_points = points.n_points
    if total_points == 0:
        return points
    target_points = max(1, int(glyph_count))
    if target_points >= total_points:
        return points
    step = max(1, total_points // target_points)
    indices = list(range(0, total_points, step))
    sampled = pv.PolyData(points.points[indices])
    for name in points.point_data.keys():
        sampled.point_data[name] = points.point_data[name][indices]
    return sampled


def _point_cloud(mesh: pv.DataSet) -> pv.PolyData:
    if isinstance(mesh, pv.PolyData):
        points = pv.PolyData(mesh.points.copy())
        for name in mesh.point_data.keys():
            points.point_data[name] = mesh.point_data[name]
        return points

    points = pv.PolyData(mesh.points.copy())
    for name in mesh.point_data.keys():
        points.point_data[name] = mesh.point_data[name]
    return points


def _vector_magnitudes(values) -> object:
    import numpy as np

    return np.linalg.norm(values, axis=1)
