# CBCL Model Viewer Agent Guide

This repository hosts the Stanford CBCL trame + PyVista companion viewer for static and time-series VTK model libraries.

## What matters most

- The main user-facing entrypoint is `python -m cbcl_model_viewer`.
- The app is a server-backed trame experience, not a static site.
- Model ingestion is folder-based: a model folder or mounted volume contains `model.yaml` plus `.vtp` / `.vtu` files, with optional `.glb` / `.usdz` assets.
- Large `.vtu` files are visualized through derived surface cache files; contributors should not hand-author those cache outputs.
- The external Fontan demo data lives outside the repo at `/Users/aaronbrown/Downloads/Fontan_sim_results_example/`.

## Repo map

- `src/cbcl_model_viewer/app.py`
  Trame app entrypoint, UI layout, playback behavior, and controller wiring.
- `src/cbcl_model_viewer/models.py`
  YAML metadata loading, validation, model discovery, and asset URL helpers.
- `src/cbcl_model_viewer/cache.py`
  Surface cache generation and reuse for heavy VTK sources.
- `src/cbcl_model_viewer/scene.py`
  PyVista plotter setup and timestep/part rendering logic.
- `src/cbcl_model_viewer/widgets.py`
  Custom `model-viewer` wrapper for optional AR previews.
- `tests/test_metadata.py`
  Metadata and discovery behavior tests.
- `tests/test_cache.py`
  Derived surface cache behavior tests.
- `examples/fontan/model.yaml`
  Template metadata for the external Fontan demo.
- `docs/deployment.md`
  Docker and reverse-proxy deployment notes.
- `docker-compose.yml`
  Local Docker smoke configuration using the external Fontan folder mount.

## Safe editing rules

- Do not check large simulation inputs into this repo. Keep heavyweight datasets external and mount them.
- Do not hand-edit files under `.cbcl-cache*`; they are derived cache artifacts and should stay ignored.
- If you change model metadata semantics, update both `README.md` and `tests/test_metadata.py`.
- If you change cache invalidation or surface extraction behavior, update `tests/test_cache.py` and rerun the cache smoke path.
- Keep the app independent from `ar-models`; optional AR assets should come from the current model folder metadata, not from another repo’s manifest.

## Common workflows

### Run the app locally

```bash
cd /Users/aaronbrown/Desktop/Github/cbcl-model-viewer
PYTHONPATH=src /Users/aaronbrown/Desktop/Github/trame-tutorial/.venv/bin/python -m cbcl_model_viewer \
  --models /Users/aaronbrown/Downloads/Fontan_sim_results_example \
  --cache .cbcl-cache \
  --port 8080
```

### Run unit tests

```bash
cd /Users/aaronbrown/Desktop/Github/cbcl-model-viewer
PYTHONPATH=src /Users/aaronbrown/Desktop/Github/trame-tutorial/.venv/bin/python -m unittest discover -s tests -v
```

### Compile-check the package

```bash
cd /Users/aaronbrown/Desktop/Github/cbcl-model-viewer
PYTHONPATH=src /Users/aaronbrown/Desktop/Github/trame-tutorial/.venv/bin/python -m compileall -q src tests
```

### Smoke-test the Fontan render path

```bash
cd /Users/aaronbrown/Desktop/Github/cbcl-model-viewer
PYTHONPATH=src /Users/aaronbrown/Desktop/Github/trame-tutorial/.venv/bin/python - <<'PY'
from cbcl_model_viewer.models import discover_models
from cbcl_model_viewer.cache import SurfaceCache
from cbcl_model_viewer.scene import ModelScene
model = discover_models('/Users/aaronbrown/Downloads/Fontan_sim_results_example')[0]
scene = ModelScene(SurfaceCache('/Users/aaronbrown/Desktop/Github/cbcl-model-viewer/.cbcl-cache-smoke'))
scene.load_model(model, timestep_index=0)
scene.plotter.render()
print(model.id, model.timestep_labels, len(scene.plotter.renderer.actors))
PY
```

### Validate Docker compose syntax

```bash
cd /Users/aaronbrown/Desktop/Github/cbcl-model-viewer
docker compose config
```

If `docker compose build` fails with a Docker daemon connection error, report that explicitly rather than claiming a container smoke test passed.

## User interaction expectations

- Treat `model.yaml` as the contributor contract. If the user asks to add a model, prefer updating or creating metadata rather than inventing a separate registration layer.
- Preserve the existing visual language: Stanford CBCL editorial styling, warm paper/sky background, red accent, and restrained control density.
- Keep the viewer minimal unless the user explicitly asks for more scientific controls. Advanced analysis features like clipping, contours, field pickers, and slices are intentionally deferred.
- When touching playback or part visibility, browser-check the trame UI rather than relying only on imports or pure Python smoke tests.

## Known quirks

- PyVista emits an offscreen/X server warning in this environment even when offscreen rendering succeeds. That warning alone is not a failure.
- Local trame server binding may require escalation in this environment for browser checks.
- The external Fontan folder now includes `/Users/aaronbrown/Downloads/Fontan_sim_results_example/model.yaml`; keep that file aligned with the example in this repo if metadata fields evolve.
- `docker compose config` can pass even when `docker compose build` is blocked by a stopped Docker daemon.

## When updating documentation

- Keep `README.md` focused on human setup, usage, and model-folder conventions.
- Keep this file focused on agent maintenance workflows, verification steps, and repo-specific hazards.
