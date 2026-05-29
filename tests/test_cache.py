from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pyvista as pv

from cbcl_model_viewer.cache import SurfaceCache, _subsample_points


class SurfaceCacheTests(unittest.TestCase):
    def test_subsample_points_uses_full_volume_points(self):
        volume = pv.ImageData(dimensions=(5, 5, 5), spacing=(0.25, 0.25, 0.25)).cast_to_unstructured_grid()
        volume.point_data["Velocity"] = np.column_stack(
            (np.ones(volume.n_points), np.zeros(volume.n_points), np.zeros(volume.n_points))
        )

        sampled = _subsample_points(volume, volume.n_points)

        self.assertEqual(sampled.n_points, volume.n_points)

    def test_creates_and_reuses_surface_cache_for_vtu_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "volume.vtu"
            volume = pv.Cube().triangulate().delaunay_3d()
            volume.point_data["Pressure"] = np.arange(volume.n_points)
            volume.save(source)
            cache = SurfaceCache(root / "cache")

            surface_path = cache.surface_for(
                source,
                model_id="fontan-example",
                part_id="flow",
                timestep_index=0,
            )
            cached_mtime = surface_path.stat().st_mtime_ns
            reused_path = cache.surface_for(
                source,
                model_id="fontan-example",
                part_id="flow",
                timestep_index=0,
            )

            self.assertEqual(surface_path, reused_path)
            self.assertEqual(cached_mtime, reused_path.stat().st_mtime_ns)
            surface = pv.read(surface_path)
            self.assertIsInstance(surface, pv.PolyData)
            self.assertIn("Pressure", surface.point_data)

    def test_creates_and_reuses_glyph_and_streamline_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "flow.vtu"
            volume = pv.ImageData(dimensions=(5, 5, 5), spacing=(0.25, 0.25, 0.25)).cast_to_unstructured_grid()
            coords = volume.points
            volume.point_data["Pressure"] = coords[:, 0] + coords[:, 1]
            vectors = np.column_stack((np.ones(volume.n_points), np.zeros(volume.n_points), np.zeros(volume.n_points)))
            volume.point_data["Velocity"] = vectors
            volume.save(source)
            cache = SurfaceCache(root / "cache")

            glyph_path = cache.glyphs_for(
                source,
                model_id="flow-demo",
                part_id="domain",
                timestep_index=0,
                preset_id="velocity-glyphs",
                vectors="Velocity",
                scale_factor=0.2,
                glyph_count=40,
            )
            streamlines_path = cache.streamlines_for(
                source,
                model_id="flow-demo",
                part_id="domain",
                timestep_index=0,
                preset_id="velocity-lines",
                vectors="Velocity",
                seed_center=(0.25, 0.25, 0.25),
                seed_radius=0.15,
                seed_points=12,
                tube_radius=0.01,
            )
            reused_streamlines = cache.streamlines_for(
                source,
                model_id="flow-demo",
                part_id="domain",
                timestep_index=0,
                preset_id="velocity-lines",
                vectors="Velocity",
                seed_center=(0.25, 0.25, 0.25),
                seed_radius=0.15,
                seed_points=12,
                tube_radius=0.01,
            )

            self.assertEqual(streamlines_path, reused_streamlines)
            self.assertGreater(pv.read(glyph_path).n_points, 0)
            self.assertGreater(pv.read(streamlines_path).n_points, 0)
            glyphs = pv.read(glyph_path)
            self.assertTrue("Pressure" in glyphs.point_data or "Pressure" in glyphs.cell_data)
            self.assertIn("Velocity_magnitude", glyphs.point_data)


if __name__ == "__main__":
    unittest.main()
