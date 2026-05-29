# CBCL Model Viewer

A trame + PyVista companion site for interactive visualization of CBCL VTK model libraries. It supports static or time-series `.vtp` / `.vtu` datasets, optional `.glb` / `.usdz` AR assets, and metadata-driven velocity glyph and streamline overlays.

## Quick start

Then open `http://localhost:8080`. The home page shows one card per model; clicking a card opens the full viewer.

For a fresh environment:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
cbcl-model-viewer --models /path/to/model-library --cache .cbcl-cache --port 8080
```

## Model folders

The app treats adding a model as a file operation: add a folder containing VTP/VTU files plus `model.yaml`. Optional AR assets can live in the same folder.

```text
models/
  fontan-example/
    model.yaml
    result_7200.vtu
    result_7232.vtu
    result_7264.vtu
    preview.glb
    preview.usdz
```

`model.yaml`:

```yaml
id: fontan-example
title: Fontan Example
description: Three-timestep simulation result.
default_scalar:
  name: Velocity
  mode: magnitude
ar:
  glb: preview.glb
  usdz: preview.usdz
visualizations:
  glyphs:
    - id: velocity-glyphs
      label: Velocity glyphs
      part: flow
      vectors: Velocity
      scale_factor: 0.01
      density: 5000
      color_by:
        name: Velocity
        mode: magnitude
parts:
  - id: flow
    label: Flow domain
    color: "#8C1515"
    files:
      - path: result_7200.vtu
        label: "7200"
      - path: result_7232.vtu
        label: "7232"
      - path: result_7264.vtu
        label: "7264"
```

Notes:

- V1 supports `.vtp` and `.vtu` visualization files.
- Static models use one file per part.
- Time-series models use multiple files in each part. Parts with one file remain visible for every timestep.
- `default_scalar.mode: magnitude` is useful for vector arrays such as `Velocity`, `WSS`, `Traction`, or `Vorticity`.
- `.glb` and `.usdz` assets are optional. When present, the app shows an AR preview and open/download actions.
- Glyph presets are vector-field arrow overlays tied to a named part and vector array.
- Streamline presets are seeded in metadata and support a lightweight density control in the viewer.

## Fontan demo

The large Fontan example data is intentionally not copied into this repo. A `model.yaml` has been added beside the files at:

```text
/Users/aaronbrown/Downloads/Fontan_sim_results_example/model.yaml
```

Run the app against that folder with:

```bash
PYTHONPATH=src /Users/aaronbrown/Desktop/Github/trame-tutorial/.venv/bin/python -m cbcl_model_viewer \
  --models /Users/aaronbrown/Downloads/Fontan_sim_results_example \
  --cache /Users/aaronbrown/Desktop/Github/cbcl-model-viewer/.cbcl-cache
```

The first view may take a few seconds because the app extracts lightweight surface caches from the original VTU files. Later views reuse those cache files until a source file changes.

## Docker

Build and run:

```bash
docker compose build
docker compose up
```

The compose file mounts `/Users/aaronbrown/Downloads/Fontan_sim_results_example` into `/app/models` and stores derived cache files in a named volume.

For another deployment:

```bash
docker run --rm -p 8080:8080 \
  -e CBCL_MODEL_LIBRARY=/app/models \
  -e CBCL_CACHE_DIR=/app/cache \
  -v /path/to/models:/app/models:ro \
  -v cbcl-model-cache:/app/cache \
  cbcl-model-viewer
```

The Docker setup is CPU/offscreen-first. If cloud performance requires GPU rendering, follow Kitware’s trame deployment guidance for EGL/GPU images and keep websocket proxying enabled.

## Deploying in the cloud

The simplest production path is a small Docker VM or container host with mounted model and cache volumes:

1. Build the image locally or in CI.
2. Push it to a registry that your cloud host can pull from.
3. Provision a VM or container service with port `8080` exposed internally.
4. Mount your model library at `/app/models` read-only and a persistent cache volume at `/app/cache` read-write.
5. Run the container with `CBCL_MODEL_LIBRARY=/app/models` and `CBCL_CACHE_DIR=/app/cache`.
6. Put NGINX, Caddy, or Traefik in front of it for HTTPS and websocket forwarding.

A plain `docker run` shape looks like this:

```bash
docker run -d --name cbcl-model-viewer -p 8080:8080 \
  -e CBCL_MODEL_LIBRARY=/app/models \
  -e CBCL_CACHE_DIR=/app/cache \
  -v /srv/cbcl-models:/app/models:ro \
  -v /srv/cbcl-cache:/app/cache \
  cbcl-model-viewer:latest
```

For a full VPS recipe plus an NGINX example, see [docs/deployment.md](/Users/aaronbrown/Desktop/Github/cbcl-model-viewer/docs/deployment.md).

## Reverse proxy notes

trame uses websockets, so production proxies must preserve websocket upgrade headers and allow long-lived connections. Kitware’s deployment docs cover the cloud/Docker/NGINX shape:

- https://kitware.github.io/trame/guide/deployment/cloud.html
- https://kitware.github.io/trame/guide/deployment/docker.html
- https://kitware.github.io/trame/guide/deployment/nginx.html

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
