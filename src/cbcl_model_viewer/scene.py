from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista as pv

from .cache import SurfaceCache
from .models import ModelMetadata

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
    ) -> None:
        self.plotter.clear()
        visible = visible_parts or {part.id for part in model.parts}

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
            self.plotter.add_mesh(
                mesh,
                name=part.id,
                color=None if scalar_name else mesh_color,
                scalars=scalar_name,
                cmap="viridis" if scalar_name else None,
                show_scalar_bar=bool(scalar_name),
                smooth_shading=True,
                reset_camera=False,
            )

        self.plotter.add_axes()
        self.plotter.reset_camera()


def _apply_default_scalar(mesh: pv.DataSet, name: str | None, mode: str) -> str | None:
    if not name:
        return None
    container = mesh.point_data if name in mesh.point_data else mesh.cell_data if name in mesh.cell_data else None
    if container is None:
        return None

    values = container[name]
    if mode == "magnitude" and getattr(values, "ndim", 1) > 1:
        scalar_name = f"{name}_magnitude"
        container[scalar_name] = np.linalg.norm(values, axis=1)
        return scalar_name
    return name


def default_cache_root() -> Path:
    return Path.home() / ".cache" / "cbcl-model-viewer" / "surfaces"
