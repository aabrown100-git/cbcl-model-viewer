from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista as pv

from .cache import SurfaceCache
from .models import GlyphPreset, ModelMetadata, StreamlinePreset

DEFAULT_COLORS = [
    "#C9362D",
    "#2D6DCC",
    "#E68D2C",
    "#6E4CD8",
    "#0D8A6E",
    "#D84CA4",
    "#2C9AB7",
    "#8C5C2A",
]


class ModelScene:
    """Own the PyVista plotter used by the trame UI."""

    def __init__(self, cache: SurfaceCache):
        pv.OFF_SCREEN = True
        self.cache = cache
        self.plotter = pv.Plotter()
        self.plotter.set_background("#f7f0df", top="#edf4f8")

    def load_model(
        self,
        model: ModelMetadata,
        *,
        timestep_index: int = 0,
        visible_parts: set[str] | None = None,
        glyph_states: dict[str, dict[str, object]] | None = None,
        streamline_states: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.plotter.clear()
        visible = visible_parts or {part.id for part in model.parts}
        glyph_states = glyph_states or {}
        streamline_states = streamline_states or {}
        glyph_part_ids = {
            preset.part_id
            for preset in model.glyphs
            if glyph_states.get(preset.id, {}).get("enabled")
        }
        streamline_part_ids = {
            preset.part_id
            for preset in model.streamlines
            if streamline_states.get(preset.id, {}).get("enabled")
        }
        scalar_bar_added = False

        for index, part in enumerate(model.parts):
            if part.id not in visible:
                continue
            part_file = part.file_for_timestep(timestep_index)
            surface_path = self.cache.surface_for(
                part_file.path,
                model_id=model.id,
                part_id=part.id,
                timestep_index=timestep_index,
            )
            mesh = pv.read(surface_path)
            scalar_name = _apply_default_scalar(mesh, model.default_scalar.name, model.default_scalar.mode)
            mesh_color = part.color or DEFAULT_COLORS[index % len(DEFAULT_COLORS)]
            if part.id in streamline_part_ids:
                base_opacity = 0.08
            elif part.id in glyph_part_ids:
                base_opacity = 0.14
            else:
                base_opacity = 1.0
            self.plotter.add_mesh(
                mesh,
                name=part.id,
                color=None if scalar_name else mesh_color,
                scalars=scalar_name,
                cmap="viridis" if scalar_name else None,
                show_scalar_bar=bool(scalar_name) and not scalar_bar_added,
                opacity=base_opacity,
                smooth_shading=True,
                reset_camera=False,
            )
            scalar_bar_added = scalar_bar_added or bool(scalar_name)

        for preset in model.glyphs:
            if preset.part_id not in visible:
                continue
            state = glyph_states.get(preset.id, {})
            if not state.get("enabled"):
                continue
            glyph_count = max(1, int(state.get("glyph_count", _default_glyph_count(model, preset, timestep_index))))
            self._add_glyphs(
                model,
                preset,
                timestep_index,
                glyph_count,
                vectors=str(state.get("vectors") or preset.vectors),
                scale_factor=float(state.get("scale_factor", preset.scale_factor)),
                color_by=state.get("color_by"),
            )

        for preset in model.streamlines:
            if preset.part_id not in visible:
                continue
            state = streamline_states.get(preset.id, {})
            if not state.get("enabled"):
                continue
            self._add_streamlines(
                model,
                preset,
                timestep_index,
                max(0.5, float(state.get("density", 1.0))),
            )

        self.plotter.add_axes()
        self.plotter.reset_camera()

    def _add_glyphs(
        self,
        model: ModelMetadata,
        preset: GlyphPreset,
        timestep_index: int,
        glyph_count: int,
        *,
        vectors: str | None = None,
        scale_factor: float | None = None,
        color_by: dict[str, object] | None = None,
    ) -> None:
        part = model.part_by_id(preset.part_id)
        part_file = part.file_for_timestep(timestep_index)
        active_vectors = vectors or preset.vectors
        active_scale_factor = scale_factor if scale_factor is not None else preset.scale_factor
        glyph_path = self.cache.glyphs_for(
            part_file.path,
            model_id=model.id,
            part_id=part.id,
            timestep_index=timestep_index,
            preset_id=preset.id,
            vectors=active_vectors,
            scale_factor=active_scale_factor,
            glyph_count=glyph_count,
        )
        glyphs = pv.read(glyph_path)
        color_name = None
        color_mode = "scalar"
        if color_by:
            color_name = color_by.get("name") or None
            color_mode = str(color_by.get("mode", "scalar"))
        elif preset.color_by.name:
            color_name = preset.color_by.name
            color_mode = preset.color_by.mode
        elif not preset.color:
            color_name = active_vectors
            color_mode = "magnitude"
        scalar_name = _apply_default_scalar(glyphs, color_name, color_mode)
        scalar_bar_title = _scalar_bar_title(color_name, color_mode, scalar_name)
        self.plotter.add_mesh(
            glyphs,
            name=f"analysis-glyphs-{preset.id}",
            scalars=scalar_name,
            color=None if scalar_name else (preset.color or "#D96C3A"),
            cmap="plasma" if scalar_name else None,
            opacity=1.0,
            smooth_shading=True,
            show_scalar_bar=bool(scalar_name),
            scalar_bar_args={"title": scalar_bar_title} if scalar_name and scalar_bar_title else None,
            reset_camera=False,
        )

    def _add_streamlines(
        self,
        model: ModelMetadata,
        preset: StreamlinePreset,
        timestep_index: int,
        density: float,
    ) -> None:
        part = model.part_by_id(preset.part_id)
        part_file = part.file_for_timestep(timestep_index)
        seed_points = max(8, int(round(preset.seed.points * density)))
        streamline_path = self.cache.streamlines_for(
            part_file.path,
            model_id=model.id,
            part_id=part.id,
            timestep_index=timestep_index,
            preset_id=preset.id,
            vectors=preset.vectors,
            seed_center=preset.seed.center,
            seed_radius=preset.seed.radius,
            seed_points=seed_points,
            tube_radius=preset.tube_radius,
        )
        streamlines = pv.read(streamline_path)
        scalar_name = _apply_default_scalar(
            streamlines,
            preset.color_by.name,
            preset.color_by.mode,
        )
        self.plotter.add_mesh(
            streamlines,
            name=f"analysis-streamline-{preset.id}",
            scalars=scalar_name,
            color=None if scalar_name else "#12B5CB",
            cmap="coolwarm" if scalar_name else None,
            ambient=0.25,
            diffuse=0.85,
            specular=0.35,
            smooth_shading=True,
            show_scalar_bar=bool(scalar_name),
            reset_camera=False,
        )


def _apply_default_scalar(mesh: pv.DataSet, name: str | None, mode: str) -> str | None:
    if not name:
        return None
    if mode == "magnitude":
        derived_name = f"{name}_magnitude"
        if derived_name in mesh.point_data or derived_name in mesh.cell_data:
            return derived_name
    container = mesh.point_data if name in mesh.point_data else mesh.cell_data if name in mesh.cell_data else None
    if container is None:
        return None

    values = container[name]
    if mode == "magnitude" and getattr(values, "ndim", 1) > 1:
        scalar_name = f"{name}_magnitude"
        container[scalar_name] = np.linalg.norm(values, axis=1)
        return scalar_name
    return name


def _scalar_bar_title(name: str | None, mode: str, scalar_name: str | None) -> str | None:
    if not scalar_name:
        return None
    if not name:
        return scalar_name
    if mode == "magnitude":
        return f"{name} magnitude"
    return name


def default_cache_root() -> Path:
    return Path.home() / ".cache" / "cbcl-model-viewer" / "surfaces"


def _default_glyph_count(model: ModelMetadata, preset: GlyphPreset, timestep_index: int) -> int:
    part = model.part_by_id(preset.part_id)
    mesh = pv.read(part.file_for_timestep(timestep_index).path)
    total_points = mesh.n_points
    if preset.density <= 1.0:
        return max(1, int(round(total_points * preset.density)))
    return max(1, int(round(preset.density)))
