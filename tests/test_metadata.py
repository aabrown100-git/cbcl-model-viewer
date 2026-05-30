from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from cbcl_model_viewer.models import (
    MetadataError,
    discover_models,
    load_model_metadata,
)


class MetadataTests(unittest.TestCase):
    def test_loads_static_model_with_optional_ar_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "heart.vtp").write_text("<VTKFile></VTKFile>")
            (root / "heart.glb").write_bytes(b"glb")
            (root / "heart.usdz").write_bytes(b"usdz")
            self._write_yaml(
                root / "model.yaml",
                {
                    "id": "static-heart",
                    "title": "Static Heart",
                    "description": "Single static part.",
                    "default_scalar": {"name": "Pressure", "mode": "scalar"},
                    "ar": {"glb": "heart.glb", "usdz": "heart.usdz"},
                    "visualizations": {
                        "glyphs": [
                            {
                                "id": "velocity-glyphs",
                                "label": "Velocity glyphs",
                                "part": "heart",
                                "vectors": "Velocity",
                                "scale_factor": 0.6,
                                "density": 0.3,
                                "color_by": {"name": "Pressure", "mode": "scalar"},
                            }
                        ],
                    },
                    "parts": [
                        {
                            "id": "heart",
                            "label": "Heart",
                            "color": "#8C1515",
                            "files": [{"path": "heart.vtp", "label": "Static"}],
                        }
                    ],
                },
            )

            model = load_model_metadata(root / "model.yaml")

            self.assertEqual(model.id, "static-heart")
            self.assertEqual(model.title, "Static Heart")
            self.assertFalse(model.is_time_series)
            self.assertEqual(model.timestep_labels, ["Static"])
            self.assertEqual(model.default_scalar.name, "Pressure")
            self.assertEqual(model.ar_assets.glb, (root / "heart.glb").resolve())
            self.assertEqual(model.parts[0].files[0].path, (root / "heart.vtp").resolve())
            self.assertEqual(model.glyphs[0].part_id, "heart")
            self.assertEqual(model.glyphs[0].color_by.name, "Pressure")

    def test_loads_time_series_model_and_discovers_model_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp)
            model_dir = library / "fontan"
            model_dir.mkdir()
            for name in ("result_7200.vtu", "result_7232.vtu", "result_7264.vtu"):
                (model_dir / name).write_text("<VTKFile></VTKFile>")
            self._write_yaml(
                model_dir / "model.yaml",
                {
                    "id": "fontan-example",
                    "title": "Fontan Example",
                    "description": "Three timesteps.",
                    "default_scalar": {"name": "Velocity", "mode": "magnitude"},
                    "parts": [
                        {
                            "id": "flow",
                            "label": "Flow domain",
                            "files": [
                                {"path": "result_7200.vtu", "label": "7200"},
                                {"path": "result_7232.vtu", "label": "7232"},
                                {"path": "result_7264.vtu", "label": "7264"},
                            ],
                        }
                    ],
                },
            )

            models = discover_models(library)

            self.assertEqual([model.id for model in models], ["fontan-example"])
            self.assertTrue(models[0].is_time_series)
            self.assertEqual(models[0].timestep_labels, ["7200", "7232", "7264"])

    def test_rejects_missing_model_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_yaml(
                root / "model.yaml",
                {
                    "id": "missing",
                    "title": "Missing",
                    "parts": [
                        {
                            "id": "part",
                            "files": [{"path": "missing.vtu", "label": "Missing"}],
                        }
                    ],
                },
            )

            with self.assertRaisesRegex(MetadataError, "does not exist"):
                load_model_metadata(root / "model.yaml")

    def test_rejects_unsupported_vtk_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "heart.stl").write_text("solid")
            self._write_yaml(
                root / "model.yaml",
                {
                    "id": "bad-format",
                    "title": "Bad Format",
                    "parts": [
                        {
                            "id": "part",
                            "files": [{"path": "heart.stl", "label": "Static"}],
                        }
                    ],
                },
            )

            with self.assertRaisesRegex(MetadataError, "Unsupported VTK file"):
                load_model_metadata(root / "model.yaml")

    def test_rejects_invalid_yaml_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.yaml"
            path.write_text("- not\n- an\n- object\n")

            with self.assertRaisesRegex(MetadataError, "top-level mapping"):
                load_model_metadata(path)

    def test_rejects_visualizations_with_unknown_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "heart.vtp").write_text("<VTKFile></VTKFile>")
            self._write_yaml(
                root / "model.yaml",
                {
                    "id": "bad-vis",
                    "title": "Bad vis",
                    "visualizations": {
                        "glyphs": [
                            {
                                "id": "bad-glyphs",
                                "part": "missing-part",
                                "vectors": "Velocity",
                            }
                        ]
                    },
                    "parts": [{"id": "heart", "files": [{"path": "heart.vtp"}]}],
                },
            )

            with self.assertRaisesRegex(MetadataError, "unknown part"):
                load_model_metadata(root / "model.yaml")

    @staticmethod
    def _write_yaml(path: Path, payload: dict[str, object]) -> None:
        path.write_text(yaml.safe_dump(payload, sort_keys=False))


if __name__ == "__main__":
    unittest.main()
