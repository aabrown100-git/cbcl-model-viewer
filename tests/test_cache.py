from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pyvista as pv

from cbcl_model_viewer.cache import SurfaceCache


class SurfaceCacheTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
