from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import pyvista as pv
from pyvista.trame.ui import plotter_ui
from trame.app import TrameApp
from trame.decorators import change
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import html
from trame.widgets import vuetify3 as v3
from trame_server.utils import asynchronous

from .cache import SurfaceCache
from .models import GlyphPreset, ModelMetadata, discover_models
from .scene import ModelScene, default_cache_root
from .widgets import ModelViewer

MODEL_VIEWER_CDN = "https://ajax.googleapis.com/ajax/libs/model-viewer/3.1.1/model-viewer.min.js"
DEFAULT_LIBRARY = Path(os.environ.get("CBCL_MODEL_LIBRARY", "/app/models"))
DEFAULT_CACHE = Path(os.environ.get("CBCL_CACHE_DIR", str(default_cache_root())))


class CBCLModelViewerApp(TrameApp):
    def __init__(
        self,
        *,
        model_library: str | Path = DEFAULT_LIBRARY,
        cache_dir: str | Path = DEFAULT_CACHE,
        server=None,
    ):
        pv.OFF_SCREEN = True
        super().__init__(server, client_type="vue3")
        self.library_root = Path(model_library).expanduser().resolve()
        self.cache = SurfaceCache(cache_dir)
        self.models = discover_models(self.library_root)
        self.models_by_id = {model.id: model for model in self.models}
        self.scene = ModelScene(self.cache)
        self.view = None
        self._play_task_running = False

        self.server.enable_module(
            {
                "module_scripts": [MODEL_VIEWER_CDN],
                "serve": {"/model-assets": str(self.library_root)},
            }
        )
        self.ctrl.start_playback = self.start_playback
        self.ctrl.stop_playback = self.stop_playback
        self.ctrl.select_model = self.open_model
        self.ctrl.open_model = self.open_model
        self.ctrl.show_home = self.show_home
        self.ctrl.refresh_scene = self._load_selected_scene
        self._initialize_state()
        self._build_ui()

    def _initialize_state(self) -> None:
        self.state.trame__title = "CBCL Model Viewer"
        self.state.model_summaries = [model.summary() for model in self.models]
        self.state.current_page = "home"
        self.state.selected_model_id = ""
        self.state.selected_title = "CBCL Model Viewer"
        self.state.selected_description = ""
        self.state.selected_kind = ""
        self.state.selected_timestep_count = 0
        self.state.selected_timestep_index = 0
        self.state.selected_timestep_label = ""
        self.state.selected_timestep_max = 0
        self.state.selected_parts = []
        self.state.visible_parts = []
        self.state.available_glyphs = []
        self.state.active_glyph_id = ""
        self.state.active_glyph_label = ""
        self.state.glyph_enabled = False
        self.state.glyph_count = 1
        self.state.glyph_scale_factor = 1.0
        self.state.available_glyph_vector_arrays = []
        self.state.active_glyph_vectors = ""
        self.state.available_glyph_color_arrays = []
        self.state.active_glyph_color_by = "__solid__"
        self.state.playing = False
        self.state.has_ar = False
        self.state.selected_ar_glb_url = ""
        self.state.selected_ar_usdz_url = ""
        self.state.error_message = "" if self.models else f"No model.yaml files found in {self.library_root}"

    def show_home(self) -> None:
        self.stop_playback()
        self.state.current_page = "home"

    def open_model(self, model_id: str) -> None:
        if model_id not in self.models_by_id:
            self.state.error_message = f"Unknown model: {model_id}"
            self.show_home()
            return
        self.stop_playback()
        self.select_model(model_id)
        self.state.current_page = "model"

    def select_model(self, model_id: str) -> None:
        model = self.models_by_id[model_id]
        all_parts = [part.id for part in model.parts]
        self.state.selected_model_id = model.id
        self.state.selected_title = model.title
        self.state.selected_description = model.description
        self.state.selected_kind = "Time series" if model.is_time_series else "Static"
        self.state.selected_timestep_count = model.timestep_count
        self.state.selected_timestep_index = 0
        self.state.selected_timestep_max = max(model.timestep_count - 1, 0)
        self.state.selected_timestep_label = model.timestep_labels[0]
        self.state.selected_parts = [{"title": part.label, "value": part.id} for part in model.parts]
        self.state.visible_parts = all_parts
        self._initialize_glyph_state(model)
        self.state.has_ar = model.ar_assets.has_assets
        self.state.selected_ar_glb_url = model.asset_url(model.ar_assets.glb)
        self.state.selected_ar_usdz_url = model.asset_url(model.ar_assets.usdz)
        self.state.error_message = ""
        self._load_selected_scene()

    def _build_glyph_options(self, model: ModelMetadata) -> list[dict[str, object]]:
        return [
            {
                "id": preset.id,
                "title": preset.label,
                "scale_factor": preset.scale_factor,
            }
            for preset in model.glyphs
        ]

    def _initialize_glyph_state(self, model: ModelMetadata) -> None:
        glyph_options = self._build_glyph_options(model)
        self.state.available_glyphs = glyph_options
        self.state.glyph_enabled = False
        if glyph_options:
            first = glyph_options[0]
            self.state.active_glyph_id = str(first["id"])
            self.state.active_glyph_label = str(first["title"])
            self.state.glyph_scale_factor = float(first["scale_factor"])
        else:
            self.state.active_glyph_id = ""
            self.state.active_glyph_label = ""
            self.state.glyph_count = 1
            self.state.glyph_scale_factor = 1.0
        self._refresh_glyph_controls(model, reset_values=True)

    @change("selected_timestep_index")
    def _on_timestep_change(self, selected_timestep_index, **_):
        if not self.state.selected_model_id:
            return
        self.show_timestep(int(selected_timestep_index))

    @change("visible_parts")
    def _on_visible_parts_change(self, **_):
        if self.state.current_page == "model" and self.state.selected_model_id:
            self._load_selected_scene()

    @change("active_glyph_id")
    def _on_active_glyph_change(self, active_glyph_id, **_):
        for item in self.state.available_glyphs or []:
            if item["id"] == active_glyph_id:
                self.state.active_glyph_label = str(item["title"])
                self.state.glyph_scale_factor = float(item["scale_factor"])
                break
        model = self.models_by_id.get(self.state.selected_model_id)
        if model:
            self._refresh_glyph_controls(model, reset_values=True)
        if self.state.current_page == "model" and self.state.selected_model_id:
            self._load_selected_scene()

    @change("glyph_enabled", "glyph_count", "glyph_scale_factor", "active_glyph_vectors", "active_glyph_color_by")
    def _on_glyph_change(self, **_):
        if self.state.current_page == "model" and self.state.selected_model_id:
            self._load_selected_scene()

    @change("playing")
    def _on_playing_change(self, playing, **_):
        if playing and not self._play_task_running:
            self._schedule_play_loop()

    def start_playback(self) -> None:
        if self.state.selected_timestep_max <= 0:
            return
        self.state.playing = True
        if not self._play_task_running:
            self._schedule_play_loop()

    def stop_playback(self) -> None:
        self.state.playing = False

    def advance_timestep(self) -> None:
        if self.state.selected_timestep_max <= 0:
            return
        next_index = (int(self.state.selected_timestep_index) + 1) % (int(self.state.selected_timestep_max) + 1)
        self.show_timestep(next_index)

    def show_timestep(self, timestep_index: int) -> None:
        model = self.models_by_id[self.state.selected_model_id]
        with self.state:
            self.state.selected_timestep_index = timestep_index
            self.state.selected_timestep_label = model.timestep_labels[timestep_index]
        self._refresh_glyph_controls(model, reset_values=False)
        self._load_selected_scene()

    def _schedule_play_loop(self) -> None:
        if self._play_task_running:
            return
        self._play_task_running = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        asynchronous.create_task(self.play_loop(), loop=loop)

    async def play_loop(self) -> None:
        try:
            while self.state.playing and self.state.selected_timestep_max > 0:
                self.advance_timestep()
                await asyncio.sleep(0.45)
        finally:
            self._play_task_running = False

    def _glyph_state(self) -> dict[str, dict[str, object]]:
        if not self.state.active_glyph_id:
            return {}
        return {
            str(self.state.active_glyph_id): {
                "enabled": bool(self.state.glyph_enabled),
                "glyph_count": max(1, int(self.state.glyph_count)),
                "vectors": str(self.state.active_glyph_vectors),
                "scale_factor": float(self.state.glyph_scale_factor),
                "color_by": self._selected_glyph_color_by(),
            }
        }

    def _selected_glyph_color_by(self) -> dict[str, str] | None:
        value = str(self.state.active_glyph_color_by or "__solid__")
        if value == "__solid__":
            return None
        name, _, mode = value.partition("|")
        return {"name": name, "mode": mode or "scalar"}

    def _refresh_glyph_controls(self, model: ModelMetadata, *, reset_values: bool) -> None:
        if not self.state.active_glyph_id:
            self.state.available_glyph_vector_arrays = []
            self.state.available_glyph_color_arrays = []
            self.state.active_glyph_vectors = ""
            self.state.active_glyph_color_by = "__solid__"
            self.state.glyph_count = 1
            return

        preset = next((item for item in model.glyphs if item.id == self.state.active_glyph_id), None)
        if preset is None:
            return
        arrays = self._dataset_array_options(model, preset.part_id)
        self.state.available_glyph_vector_arrays = arrays["vectors"]
        self.state.available_glyph_color_arrays = arrays["colors"]

        vector_values = [item["value"] for item in arrays["vectors"]]
        color_values = [item["value"] for item in arrays["colors"]]
        default_color_by = self._default_glyph_color_by_value(model, preset)

        if reset_values or self.state.active_glyph_vectors not in vector_values:
            self.state.active_glyph_vectors = preset.vectors if preset.vectors in vector_values else (vector_values[0] if vector_values else "")
        if reset_values or self.state.active_glyph_color_by not in color_values:
            self.state.active_glyph_color_by = default_color_by if default_color_by in color_values else "__solid__"
        if reset_values:
            self.state.glyph_count = self._default_glyph_count(model, preset)

    def _default_glyph_color_by_value(self, model: ModelMetadata, preset: GlyphPreset) -> str:
        if preset.color_by.name:
            return f"{preset.color_by.name}|{preset.color_by.mode}"
        if preset.color:
            return "__solid__"
        if model.default_scalar.name:
            return f"{model.default_scalar.name}|{model.default_scalar.mode}"
        return f"{preset.vectors}|magnitude"

    def _dataset_array_options(self, model: ModelMetadata, part_id: str) -> dict[str, list[dict[str, str]]]:
        part = model.part_by_id(part_id)
        source = pv.read(part.file_for_timestep(int(self.state.selected_timestep_index)).path)
        vectors: list[dict[str, str]] = []
        colors: list[dict[str, str]] = [{"title": "Solid color", "value": "__solid__"}]

        for name, values in _iter_dataset_arrays(source):
            if _is_vector_array(values):
                vectors.append({"title": name, "value": name})
                colors.append({"title": f"{name} (magnitude)", "value": f"{name}|magnitude"})
            else:
                colors.append({"title": name, "value": f"{name}|scalar"})

        return {"vectors": vectors, "colors": colors}

    def _default_glyph_count(self, model: ModelMetadata, preset: GlyphPreset) -> int:
        mesh = pv.read(model.part_by_id(preset.part_id).file_for_timestep(int(self.state.selected_timestep_index)).path)
        if preset.density <= 1.0:
            return max(1, int(round(mesh.n_points * preset.density)))
        return max(1, int(round(preset.density)))

    def _load_selected_scene(self) -> None:
        if not self.state.selected_model_id:
            return
        model = self.models_by_id[self.state.selected_model_id]
        visible = set(self.state.visible_parts or [part.id for part in model.parts])
        try:
            self.scene.load_model(
                model,
                timestep_index=int(self.state.selected_timestep_index),
                visible_parts=visible,
                glyph_states=self._glyph_state(),
            )
            if self.view:
                self.ctrl.view_update()
        except Exception as exc:  # pragma: no cover - surfaced in UI
            self.state.error_message = str(exc)

    def _build_ui(self) -> None:
        with SinglePageLayout(self.server, theme=("theme", "light")) as layout:
            self._add_style()
            layout.title.set_text("CBCL Model Viewer")

            with layout.toolbar:
                v3.VBtn(
                    icon="mdi-arrow-left",
                    variant="text",
                    click=self.ctrl.show_home,
                    v_show="current_page === 'model'",
                )
                html.Div("Stanford CBCL", classes="cbcl-eyebrow")
                v3.VSpacer()
                html.Div("{{ current_page === 'model' ? selected_title : 'Model Gallery' }}", classes="cbcl-toolbar-title")
                v3.VSpacer()
                v3.VBtn(
                    icon="mdi-crop-free",
                    variant="text",
                    click=self.ctrl.view_reset_camera,
                    v_show="current_page === 'model'",
                )

            with layout.content:
                with v3.VContainer(fluid=True, classes="cbcl-shell pa-0"):
                    self._home_page()
                    self._detail_page()
        self.ctrl.play_loop = self.play_loop

    def _home_page(self) -> None:
        with html.Div(v_show="current_page === 'home'", classes="cbcl-home"):
            with html.Div(classes="cbcl-home-hero"):
                html.Div("Computational Biomechanics and Cardiovascular Modeling", classes="cbcl-eyebrow")
                html.H1("Model library", classes="cbcl-home-title")
                html.P(
                    "Explore static anatomy, time-varying simulations, and AR-ready assets from one mounted model library.",
                    classes="cbcl-home-copy",
                )
            with html.Div(classes="cbcl-gallery"):
                if not self.models:
                    v3.VAlert(
                        "No model.yaml files found.",
                        type="warning",
                        variant="tonal",
                        density="compact",
                        classes="ma-4",
                    )
                for model in self.models:
                    self._home_card(model)

    def _home_card(self, model: ModelMetadata) -> None:
        with v3.VCard(
            classes="cbcl-gallery-card",
            variant="flat",
            click=(self.ctrl.open_model, f"['{model.id}']"),
        ):
            if model.ar_assets.glb:
                with html.Div(classes="cbcl-card-preview"):
                    ModelViewer(
                        src=model.asset_url(model.ar_assets.glb),
                        ios_src=model.asset_url(model.ar_assets.usdz),
                        auto_rotate=True,
                        camera_controls=True,
                        shadow_intensity=1,
                        style="width: 100%; height: 100%;",
                    )
            with v3.VCardText(classes="pa-4"):
                html.Div("Time series" if model.is_time_series else "Static", classes="cbcl-eyebrow")
                html.H2(model.title, classes="cbcl-card-title")
                html.P(model.description, classes="cbcl-description")
                html.P(
                    f"{len(model.parts)} part{'s' if len(model.parts) != 1 else ''} · "
                    f"{model.timestep_count} timestep{'s' if model.timestep_count != 1 else ''} · "
                    f"{len(model.glyphs)} analysis preset"
                    f"{'s' if len(model.glyphs) != 1 else ''}",
                    classes="cbcl-muted",
                )

    def _detail_page(self) -> None:
        with html.Div(v_show="current_page === 'model'", classes="fill-height"):
            with v3.VRow(classes="ma-0 fill-height", no_gutters=True):
                with v3.VCol(cols=12, md=8, classes="cbcl-viewer-col"):
                    self.view = plotter_ui(self.scene.plotter)
                    self.ctrl.view_update = self.view.update
                    self.ctrl.view_reset_camera = self.view.reset_camera
                with v3.VCol(cols=12, md=4, classes="cbcl-side-panel"):
                    self._details_panel()

    def _details_panel(self) -> None:
        with html.Div(classes="cbcl-panel-content"):
            html.Div("Interactive model", classes="cbcl-eyebrow")
            html.H1("{{ selected_title }}", classes="cbcl-title")
            html.P("{{ selected_description }}", classes="cbcl-description")
            v3.VAlert(
                "{{ error_message }}",
                type="error",
                variant="tonal",
                density="compact",
                v_show="error_message",
                classes="mb-4",
            )
            with html.Div(classes="cbcl-stat-grid"):
                html.Div("{{ selected_kind }}", classes="cbcl-stat")
                html.Div("{{ selected_timestep_count }} timestep(s)", classes="cbcl-stat")

            v3.VSelect(
                v_model=("visible_parts", []),
                items=("selected_parts", []),
                label="Visible parts",
                multiple=True,
                chips=True,
                density="compact",
                hide_details=True,
                classes="mb-4",
            )

            with html.Div(v_show="selected_timestep_max > 0", classes="mb-5"):
                with html.Div(classes="cbcl-playbar"):
                    v3.VBtn(
                        icon="mdi-play",
                        variant="tonal",
                        color="#8c1515",
                        click=self.ctrl.start_playback,
                        v_show="!playing",
                    )
                    v3.VBtn(
                        icon="mdi-pause",
                        variant="tonal",
                        color="#8c1515",
                        click=self.ctrl.stop_playback,
                        v_show="playing",
                    )
                    html.Span("{{ selected_timestep_label }}", classes="cbcl-muted")
                v3.VSlider(
                    v_model=("selected_timestep_index", 0),
                    min=0,
                    max=("selected_timestep_max", 0),
                    step=1,
                    density="compact",
                    hide_details=True,
                )

            with html.Div(v_show="available_glyphs.length", classes="cbcl-analysis-panel"):
                html.Div("Analysis", classes="cbcl-eyebrow")
                with html.Div(v_show="available_glyphs.length", classes="cbcl-analysis-card"):
                    v3.VSelect(
                        v_model=("active_glyph_id", ""),
                        items=("available_glyphs", []),
                        label="Glyph preset",
                        density="compact",
                        hide_details=True,
                        classes="mb-3",
                    )
                    with html.Div(classes="cbcl-analysis-header"):
                        html.Strong("{{ active_glyph_label }}")
                        v3.VSwitch(
                            v_model=("glyph_enabled", False),
                            density="compact",
                            hide_details=True,
                            color="#8c1515",
                            inset=True,
                        )
                    html.P(
                        "{{ active_glyph_vectors || 'No vector arrays found' }}",
                        classes="cbcl-muted mb-3",
                    )
                    v3.VSelect(
                        v_model=("active_glyph_vectors", ""),
                        items=("available_glyph_vector_arrays", []),
                        item_title="title",
                        item_value="value",
                        label="Glyph array",
                        density="compact",
                        hide_details=True,
                        classes="mb-3",
                    )
                    v3.VSelect(
                        v_model=("active_glyph_color_by", "__solid__"),
                        items=("available_glyph_color_arrays", []),
                        item_title="title",
                        item_value="value",
                        label="Color by",
                        density="compact",
                        hide_details=True,
                        classes="mb-3",
                    )
                    v3.VTextField(
                        v_model=("glyph_scale_factor", 0.01),
                        label="Glyph scale",
                        type="number",
                        min=0.0,
                        step="0.01",
                        hide_details=True,
                        density="compact",
                        classes="mb-3",
                    )
                    v3.VTextField(
                        v_model=("glyph_count", 5000),
                        label="Number of glyphs",
                        type="number",
                        min=1,
                        step=1,
                        hide_details=True,
                        density="compact",
                    )

            with html.Div(v_show="has_ar", classes="cbcl-ar-panel"):
                html.Div("AR model", classes="cbcl-eyebrow")
                with html.Div(classes="cbcl-ar-preview"):
                    ModelViewer(
                        src=("selected_ar_glb_url", ""),
                        ios_src=("selected_ar_usdz_url", ""),
                        ar=True,
                        ar_modes="webxr scene-viewer quick-look",
                        camera_controls=True,
                        shadow_intensity=1,
                        style="width: 100%; height: 100%;",
                    )
                with html.Div(classes="cbcl-actions"):
                    v3.VBtn(
                        "Open GLB",
                        href=("selected_ar_glb_url", ""),
                        target="_blank",
                        variant="flat",
                        color="#8c1515",
                        v_show="selected_ar_glb_url",
                    )
                    v3.VBtn(
                        "Open USDZ",
                        href=("selected_ar_usdz_url", ""),
                        target="_blank",
                        variant="outlined",
                        v_show="selected_ar_usdz_url",
                    )

    @staticmethod
    def _add_style() -> None:
        html.Style(
            """
            :root {
              --cbcl-ink: #101820;
              --cbcl-accent: #8c1515;
              --cbcl-paper: #fbf7ef;
              --cbcl-sky: #d7e9f8;
              --cbcl-line: rgba(16, 24, 32, 0.12);
            }
            body, .v-application {
              font-family: Georgia, "Iowan Old Style", serif;
              color: var(--cbcl-ink);
            }
            .cbcl-shell {
              min-height: calc(100vh - 64px);
              background:
                radial-gradient(circle at top right, rgba(140, 21, 21, 0.13), transparent 30rem),
                linear-gradient(180deg, var(--cbcl-paper), #f4f6f8 45%, var(--cbcl-sky));
            }
            .cbcl-eyebrow {
              color: var(--cbcl-accent);
              font-size: 0.72rem;
              letter-spacing: 0.08em;
              text-transform: uppercase;
              font-weight: 700;
            }
            .cbcl-toolbar-title {
              font-size: 0.95rem;
              font-weight: 700;
            }
            .cbcl-home {
              padding: 1.5rem 1.25rem 2rem;
            }
            .cbcl-home-hero {
              max-width: 860px;
              padding: 1rem 0 2rem;
            }
            .cbcl-home-title {
              font-size: clamp(2.4rem, 5vw, 4.6rem);
              line-height: 0.95;
              margin: 0.3rem 0 0.8rem;
            }
            .cbcl-home-copy,
            .cbcl-muted,
            .cbcl-description {
              color: rgba(16, 24, 32, 0.68);
              line-height: 1.45;
            }
            .cbcl-gallery {
              display: grid;
              grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
              gap: 1rem;
            }
            .cbcl-gallery-card,
            .cbcl-analysis-card {
              border: 1px solid var(--cbcl-line);
              border-radius: 8px;
              overflow: hidden;
              background: rgba(255, 255, 255, 0.92);
            }
            .cbcl-card-preview {
              height: 180px;
              background: linear-gradient(180deg, #f7f0df, #edf4f8);
              border-bottom: 1px solid var(--cbcl-line);
            }
            .cbcl-card-title {
              margin: 0.35rem 0;
              font-size: 1.35rem;
              line-height: 1.1;
            }
            .cbcl-viewer-col {
              min-height: calc(100vh - 64px);
              background: rgba(255, 255, 255, 0.38);
            }
            .cbcl-side-panel {
              border-left: 1px solid var(--cbcl-line);
              background: rgba(255, 255, 255, 0.84);
              overflow: auto;
              max-height: calc(100vh - 64px);
            }
            .cbcl-panel-content {
              padding: 1rem;
            }
            .cbcl-title {
              font-size: clamp(2rem, 4vw, 3.2rem);
              line-height: 0.95;
              margin: 0.4rem 0 0.75rem;
            }
            .cbcl-stat-grid {
              display: grid;
              grid-template-columns: 1fr 1fr;
              gap: 0.5rem;
              margin: 1rem 0;
            }
            .cbcl-stat {
              border: 1px solid var(--cbcl-line);
              border-radius: 6px;
              padding: 0.7rem;
              background: white;
            }
            .cbcl-playbar, .cbcl-actions, .cbcl-analysis-header {
              display: flex;
              align-items: center;
              gap: 0.75rem;
            }
            .cbcl-analysis-panel,
            .cbcl-ar-panel {
              margin-top: 1rem;
              padding-top: 1rem;
              border-top: 1px solid var(--cbcl-line);
            }
            .cbcl-analysis-card {
              padding: 0.75rem;
              margin: 0.75rem 0;
            }
            .cbcl-analysis-header {
              justify-content: space-between;
            }
            .cbcl-ar-preview {
              height: 280px;
              margin: 0.75rem 0;
              border: 1px solid var(--cbcl-line);
              border-radius: 8px;
              background: linear-gradient(180deg, #f7f0df, #edf4f8);
              overflow: hidden;
            }
            @media (max-width: 960px) {
              .cbcl-side-panel {
                max-height: none;
                border-left: 0;
                border-top: 1px solid var(--cbcl-line);
              }
            }
            """
        )


def _iter_dataset_arrays(dataset: pv.DataSet):
    seen: set[str] = set()
    for container in (dataset.point_data, dataset.cell_data):
        for name in container.keys():
            if name in seen:
                continue
            seen.add(name)
            yield name, container[name]


def _is_vector_array(values) -> bool:
    return getattr(values, "ndim", 1) > 1 and values.shape[1] >= 3


def build_app(model_library: str | Path = DEFAULT_LIBRARY, cache_dir: str | Path = DEFAULT_CACHE):
    return CBCLModelViewerApp(model_library=model_library, cache_dir=cache_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the CBCL trame/PyVista model viewer.")
    parser.add_argument("--models", default=str(DEFAULT_LIBRARY), help="Directory containing model folders or a model.yaml.")
    parser.add_argument("--cache", default=str(DEFAULT_CACHE), help="Directory for derived surface cache files.")
    parser.add_argument("--host", default=os.environ.get("TRAME_DEFAULT_HOST", "0.0.0.0"))
    parser.add_argument("--port", default=int(os.environ.get("PORT", "8080")), type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    app = build_app(model_library=args.models, cache_dir=args.cache)
    app.server.start(host=args.host, port=args.port, open_browser=False)


if __name__ == "__main__":
    main()
