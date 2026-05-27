from __future__ import annotations

from trame_client.widgets.core import AbstractElement


class ModelViewer(AbstractElement):
    """Small wrapper around Google's `<model-viewer>` web component."""

    def __init__(self, **kwargs):
        super().__init__(
            "model-viewer",
            __properties=[
                ("ios_src", "ios-src"),
                "src",
                "ar",
                ("ar_modes", "ar-modes"),
                ("camera_controls", "camera-controls"),
                ("auto_rotate", "auto-rotate"),
                ("shadow_intensity", "shadow-intensity"),
                "style",
            ],
            **kwargs,
        )
        self.attrs(
            "src",
            ("ios_src", "ios-src"),
            "ar",
            ("ar_modes", "ar-modes"),
            ("camera_controls", "camera-controls"),
            ("auto_rotate", "auto-rotate"),
            ("shadow_intensity", "shadow-intensity"),
            "style",
        )
