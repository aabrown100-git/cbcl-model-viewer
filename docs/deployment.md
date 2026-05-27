# Deployment Notes

This app follows the standard trame deployment shape: package the Python service in Docker, mount model data into the container, and expose the trame websocket server through HTTPS-capable infrastructure.

## Runtime layout

- App code: `/app`
- Model library: `/app/models`
- Derived surface cache: `/app/cache`
- Port: `8080`

Configure with environment variables:

```bash
CBCL_MODEL_LIBRARY=/app/models
CBCL_CACHE_DIR=/app/cache
TRAME_DEFAULT_HOST=0.0.0.0
TRAME_SERVER=true
PYVISTA_OFF_SCREEN=true
```

## CPU/offscreen first

The provided Docker image uses regular Python wheels and system OpenGL/EGL libraries. It is meant as a portable first deployment target. For heavier studies or many concurrent users, use a GPU/EGL-capable image following Kitware’s Docker guidance.

## Reverse proxy

trame requires websocket support. A reverse proxy must pass `Upgrade` and `Connection` headers and avoid short read timeouts. Kitware’s NGINX guidance is the reference for production hardening.

## Data management

Mount model folders as read-only when possible. Mount cache storage read-write so the app can reuse extracted surfaces across restarts.
