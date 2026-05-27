from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import pyvista as pv
from pyvista.trame.ui import plotter_ui
from trame.app import TrameApp
from trame.decorators import change
from trame.ui.vuetify3 import SinglePageWithDrawerLayout
from trame.widgets import html
from trame.widgets import vuetify3 as v3
from trame_server.utils import asynchronous

from .cache import SurfaceCache
from .models import ModelMetadata, discover_models
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
        self.ctrl.select_model = self.select_model
        self._initialize_state()
        self._build_ui()
        if self.models:
            self.select_model(self.models[0].id)

    def _initialize_state(self) -> None:
        self.state.trame__title = "CBCL Model Viewer"
        self.state.model_summaries = [model.summary() for model in self.models]
        self.state.selected_model_id = self.models[0].id if self.models else ""
        self.state.selected_title = self.models[0].title if self.models else "No models found"
        self.state.selected_description = self.models[0].description if self.models else ""
        self.state.selected_kind = ""
        self.state.selected_timestep_count = 0
        self.state.selected_timestep_index = 0
        self.state.selected_timestep_label = ""
        self.state.selected_timestep_max = 0
        self.state.selected_parts = []
        self.state.visible_parts = []
        self.state.playing = False
        self.state.has_ar = False
        self.state.selected_ar_glb_url = ""
        self.state.selected_ar_usdz_url = ""
        self.state.error_message = "" if self.models else f"No model.yaml files found in {self.library_root}"

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
        self.state.selected_parts = [
            {"title": part.label, "value": part.id} for part in model.parts
        ]
        self.state.visible_parts = all_parts
        self.state.has_ar = model.ar_assets.has_assets
        self.state.selected_ar_glb_url = model.asset_url(model.ar_assets.glb)
        self.state.selected_ar_usdz_url = model.asset_url(model.ar_assets.usdz)
        self.state.error_message = ""
        self._load_selected_scene()

    @change("selected_timestep_index")
    def _on_timestep_change(self, selected_timestep_index, **_):
        if not self.state.selected_model_id:
            return
        self.show_timestep(int(selected_timestep_index))

    @change("visible_parts")
    def _on_visible_parts_change(self, visible_parts, **_):
        if not self.state.selected_model_id:
            return
        self._load_selected_scene()

    @change("playing")
    def _on_playing_change(self, playing, **_):
        if playing and not self._play_task_running:
            self._schedule_play_loop()

    def start_playback(self) -> None:
        self.state.playing = True
        self.advance_timestep()
        if not self._play_task_running:
            self._schedule_play_loop()

    def stop_playback(self) -> None:
        self.state.playing = False

    def advance_timestep(self) -> None:
        if self.state.selected_timestep_max <= 0:
            return
        next_index = (int(self.state.selected_timestep_index) + 1) % (
            int(self.state.selected_timestep_max) + 1
        )
        self.show_timestep(next_index)

    def show_timestep(self, timestep_index: int) -> None:
        model = self.models_by_id[self.state.selected_model_id]
        with self.state:
            self.state.selected_timestep_index = timestep_index
            self.state.selected_timestep_label = model.timestep_labels[timestep_index]
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

    def _load_selected_scene(self) -> None:
        model = self.models_by_id[self.state.selected_model_id]
        visible = set(self.state.visible_parts or [part.id for part in model.parts])
        try:
            self.scene.load_model(
                model,
                timestep_index=int(self.state.selected_timestep_index),
                visible_parts=visible,
            )
            if self.view:
                self.ctrl.view_update()
        except Exception as exc:  # pragma: no cover - surfaced in UI
            self.state.error_message = str(exc)

    def _build_ui(self) -> None:
        with SinglePageWithDrawerLayout(self.server, theme=("theme", "light")) as layout:
            layout.title.set_text("CBCL Model Viewer")
            self._add_style()

            with layout.toolbar:
                html.Div("Stanford CBCL", classes="cbcl-eyebrow")
                v3.VSpacer()
                v3.VBtn(
                    icon="mdi-crop-free",
                    variant="text",
                    click=self.ctrl.view_reset_camera,
                )

            with layout.drawer as drawer:
                drawer.width = 360
                html.Div("Models", classes="cbcl-drawer-title")
                if not self.models:
                    v3.VAlert(
                        "No model.yaml files found.",
                        type="warning",
                        variant="tonal",
                        density="compact",
                        classes="ma-3",
                    )
                for model in self.models:
                    self._model_card(model)

            with layout.content:
                with v3.VContainer(fluid=True, classes="cbcl-shell pa-0 fill-height"):
                    with v3.VRow(classes="ma-0 fill-height", no_gutters=True):
                        with v3.VCol(cols=12, md=8, classes="cbcl-viewer-col"):
                            self.view = plotter_ui(
                                self.scene.plotter,
                                mode="server",
                                default_server_rendering=True,
                                add_menu=False,
                            )
                            self.ctrl.view_update = self.view.update
                            self.ctrl.view_reset_camera = self.view.reset_camera
                        with v3.VCol(cols=12, md=4, classes="cbcl-side-panel"):
                            self._details_panel()

        self.ctrl.play_loop = self.play_loop

    def _model_card(self, model: ModelMetadata) -> None:
        with v3.VCard(
            classes="cbcl-model-card ma-3",
            variant="flat",
            click=(self.ctrl.select_model, f"['{model.id}']"),
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
                html.H3(model.title, classes="cbcl-card-title")
                html.P(
                    f"{len(model.parts)} part{'s' if len(model.parts) != 1 else ''} · {model.timestep_count} timestep{'s' if model.timestep_count != 1 else ''}",
                    classes="cbcl-muted",
                )

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
            with html.Div(v_show="selected_timestep_max > 0", classes="mb-4"):
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
            .cbcl-drawer-title {
              font-size: 1.8rem;
              line-height: 1;
              padding: 1rem 1rem 0;
              font-weight: 700;
            }
            .cbcl-model-card {
              border: 1px solid var(--cbcl-line);
              border-radius: 8px;
              overflow: hidden;
              background: rgba(255, 255, 255, 0.9);
              cursor: pointer;
            }
            .cbcl-card-preview {
              height: 160px;
              background: linear-gradient(180deg, #f7f0df, #edf4f8);
              border-bottom: 1px solid var(--cbcl-line);
            }
            .cbcl-card-title {
              margin: 0.35rem 0;
              font-size: 1.2rem;
              line-height: 1.1;
            }
            .cbcl-muted, .cbcl-description {
              color: rgba(16, 24, 32, 0.68);
              line-height: 1.45;
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
            .cbcl-playbar, .cbcl-actions {
              display: flex;
              align-items: center;
              gap: 0.75rem;
            }
            .cbcl-ar-panel {
              margin-top: 1rem;
              padding-top: 1rem;
              border-top: 1px solid var(--cbcl-line);
            }
            .cbcl-ar-preview {
              height: 280px;
              margin: 0.75rem 0;
              border: 1px solid var(--cbcl-line);
              border-radius: 8px;
              background: linear-gradient(180deg, #f7f0df, #edf4f8);
              overflow: hidden;
            }
            """
        )


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
    app.server.start(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
