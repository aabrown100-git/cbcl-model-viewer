# CBCL Model Viewer

A trame + PyVista web app for interactive visualization of CBCL VTK model libraries. It supports static and time-series `.vtp` / `.vtu` datasets, metadata-driven coloring, and glyph-based vector-field visualization.

## Quick Start

This project requires Python 3.10+, one option on macOS is:

```bash
brew install python@3.11
/opt/homebrew/bin/python3.11 -m venv .venv
```


Create an environment, install the package, and launch the app:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
cbcl-model-viewer --models examples/fontan --cache .cbcl-cache --port 8080
```

Then open `http://localhost:8080`.

## Model Folder Contract

The app treats a model as a folder containing:

- `model.yaml`
- one or more `.vtp` or `.vtu` files
- optional `.glb` / `.usdz` assets for AR preview

A model library can be:

- a directory containing a single `model.yaml`
- or a parent directory containing one subdirectory per model

Supported metadata includes:

- model id, title, and description
- static or time-series part files
- default scalar coloring
- glyph presets tied to a part and vector array
- optional AR asset paths

Notes:

- Static models use one file per part.
- Time-series models use multiple files per part.
- For scalar arrays such as `Concentration`, use `default_scalar.name: Concentration` and leave `mode` as `scalar` or omit it.
- `mode: magnitude` is only needed for vector arrays such as `Velocity`, `WSS`, `Traction`, or `Vorticity`.

## Bundled Fontan Example

This repo includes a compact Fontan example under [examples/fontan](/Users/aaronbrown/Desktop/Github/cbcl-model-viewer/examples/fontan).

- two timesteps are included: `result_7200.vtu` and `result_7232.vtu`
- the `.vtu` files are tracked with Git LFS
- the example metadata lives in [examples/fontan/model.yaml](/Users/aaronbrown/Desktop/Github/cbcl-model-viewer/examples/fontan/model.yaml)

Run the app against the bundled example with:

```bash
cbcl-model-viewer --models examples/fontan --cache .cbcl-cache --port 8080
```

The first load may take a few seconds while the app derives lightweight cache files from the source VTU data. Later loads reuse that cache until the source files change.

## Testing

Run the test suite with:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Compile-check the package with:

```bash
PYTHONPATH=src python -m compileall src tests
```
