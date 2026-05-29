from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pyvista as pv
import yaml

from cbcl_model_viewer.cache import SurfaceCache
from cbcl_model_viewer.models import load_model_metadata
from cbcl_model_viewer.scene import ModelScene


class SceneTests(unittest.TestCase):
    def test_load_model_adds_glyph_actor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "flow.vtu"
            volume = pv.ImageData(dimensions=(5, 5, 5), spacing=(0.25, 0.25, 0.25)).cast_to_unstructured_grid()
            coords = volume.points
            volume.point_data["Pressure"] = coords[:, 0] + coords[:, 1]
            volume.point_data["Velocity"] = np.column_stack(
                (np.ones(volume.n_points), np.zeros(volume.n_points), np.zeros(volume.n_points))
            )
            volume.save(source)
            (root / "model.yaml").write_text(
                yaml.safe_dump(
                    {
                        "id": "flow-demo",
                        "title": "Flow demo",
                        "parts": [{"id": "domain", "files": [{"path": "flow.vtu", "label": "0"}]}],
                        "visualizations": {
                            "glyphs": [
                                {
                                    "id": "velocity-glyphs",
                                    "part": "domain",
                                    "vectors": "Velocity",
                                    "scale_factor": 0.2,
                                    "density": 0.35,
                                    "color_by": {"name": "Pressure", "mode": "scalar"},
                                }
                            ],
                        },
                    },
                    sort_keys=False,
                )
            )
            model = load_model_metadata(root / "model.yaml")
            scene = ModelScene(SurfaceCache(root / "cache"))

            scene.load_model(
                model,
                glyph_states={
                    "velocity-glyphs": {
                        "enabled": True,
                        "glyph_count": 40,
                        "vectors": "Velocity",
                        "scale_factor": 0.2,
                        "color_by": {"name": "Velocity", "mode": "magnitude"},
                    }
                },
            )

            actor_names = {key for key in scene.plotter.actors if isinstance(key, str)}
            self.assertIn("domain", actor_names)
            self.assertIn("analysis-glyphs-velocity-glyphs", actor_names)
            mapper = scene.plotter.actors["analysis-glyphs-velocity-glyphs"].GetMapper()
            self.assertEqual(mapper.GetArrayName(), "Velocity_magnitude")
            scalar_bar_titles = {actor.GetTitle() for actor in scene.plotter.scalar_bars.values()}
            self.assertIn("Velocity magnitude", scalar_bar_titles)

    def test_load_model_adds_streamline_actor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "flow.vtu"
            volume = pv.ImageData(dimensions=(5, 5, 5), spacing=(0.25, 0.25, 0.25)).cast_to_unstructured_grid()
            coords = volume.points
            volume.point_data["Pressure"] = coords[:, 0] + coords[:, 1]
            volume.point_data["Velocity"] = np.column_stack(
                (np.ones(volume.n_points), np.zeros(volume.n_points), np.zeros(volume.n_points))
            )
            volume.save(source)
            (root / "model.yaml").write_text(
                yaml.safe_dump(
                    {
                        "id": "flow-demo",
                        "title": "Flow demo",
                        "parts": [{"id": "domain", "files": [{"path": "flow.vtu", "label": "0"}]}],
                        "visualizations": {
                            "streamlines": [
                                {
                                    "id": "velocity-lines",
                                    "part": "domain",
                                    "vectors": "Velocity",
                                    "tube_radius": 0.01,
                                    "seed": {
                                        "center": [0.25, 0.25, 0.25],
                                        "radius": 0.15,
                                        "points": 12,
                                    },
                                }
                            ]
                        },
                    },
                    sort_keys=False,
                )
            )
            model = load_model_metadata(root / "model.yaml")
            scene = ModelScene(SurfaceCache(root / "cache"))

            scene.load_model(
                model,
                streamline_states={"velocity-lines": {"enabled": True, "density": 1.0}},
            )

            actor_names = {key for key in scene.plotter.actors if isinstance(key, str)}
            self.assertIn("analysis-streamline-velocity-lines", actor_names)

    def test_load_model_softens_surface_when_glyphs_are_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "flow.vtu"
            volume = pv.ImageData(dimensions=(5, 5, 5), spacing=(0.25, 0.25, 0.25)).cast_to_unstructured_grid()
            coords = volume.points
            volume.point_data["Pressure"] = coords[:, 0] + coords[:, 1]
            volume.point_data["Velocity"] = np.column_stack(
                (np.ones(volume.n_points), np.zeros(volume.n_points), np.zeros(volume.n_points))
            )
            volume.save(source)
            (root / "model.yaml").write_text(
                yaml.safe_dump(
                    {
                        "id": "flow-demo",
                        "title": "Flow demo",
                        "parts": [{"id": "domain", "files": [{"path": "flow.vtu", "label": "0"}]}],
                        "visualizations": {
                            "glyphs": [
                                {
                                    "id": "velocity-glyphs",
                                    "part": "domain",
                                    "vectors": "Velocity",
                                    "scale_factor": 0.2,
                                    "density": 0.35,
                                }
                            ]
                        },
                    },
                    sort_keys=False,
                )
            )
            model = load_model_metadata(root / "model.yaml")
            scene = ModelScene(SurfaceCache(root / "cache"))

            scene.load_model(model)
            base_opacity = scene.plotter.actors["domain"].GetProperty().GetOpacity()

            scene.load_model(
                model,
                glyph_states={"velocity-glyphs": {"enabled": True, "glyph_count": 40}},
            )
            glyph_opacity = scene.plotter.actors["domain"].GetProperty().GetOpacity()

            self.assertEqual(base_opacity, 1.0)
            self.assertLess(glyph_opacity, 1.0)


if __name__ == "__main__":
    unittest.main()
