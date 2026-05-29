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

## Generic cloud recipe

This is the lowest-friction cloud setup for the current app:

1. Build the image:

```bash
docker build -t cbcl-model-viewer:latest .
```

2. Push it to a registry your host can reach.

3. On the VM or container host, create persistent directories:

```bash
sudo mkdir -p /srv/cbcl-models /srv/cbcl-cache
```

4. Sync or mount your model folders into `/srv/cbcl-models`.

5. Run the container:

```bash
docker run -d --name cbcl-model-viewer --restart unless-stopped \
  -p 8080:8080 \
  -e CBCL_MODEL_LIBRARY=/app/models \
  -e CBCL_CACHE_DIR=/app/cache \
  -e TRAME_DEFAULT_HOST=0.0.0.0 \
  -v /srv/cbcl-models:/app/models:ro \
  -v /srv/cbcl-cache:/app/cache \
  cbcl-model-viewer:latest
```

6. Put a reverse proxy in front of `localhost:8080` for HTTPS and websocket support.

## CPU/offscreen first

The provided Docker image uses regular Python wheels and system OpenGL/EGL libraries. It is meant as a portable first deployment target. For heavier studies or many concurrent users, use a GPU/EGL-capable image following Kitware’s Docker guidance.

## Reverse proxy

trame requires websocket support. A reverse proxy must pass `Upgrade` and `Connection` headers and avoid short read timeouts. Kitware’s NGINX guidance is the reference for production hardening.

An NGINX shape looks like this:

```nginx
server {
    listen 80;
    server_name example.your-domain.org;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

If you use Caddy or Traefik instead, the same rule applies: preserve websocket upgrades and do not use short idle timeouts.

## Data management

Mount model folders as read-only when possible. Mount cache storage read-write so the app can reuse extracted surfaces across restarts.

## Notes for heavier deployments

- The current Docker path is CPU/offscreen-first and works well as a baseline.
- For large studies or more concurrent traffic, switch to a GPU/EGL-capable runtime using Kitware’s trame and VTK guidance.
- Keep the model library independent from the application image. Treat model folders as mounted content rather than baked-in assets so new studies can be published without rebuilding the container.
