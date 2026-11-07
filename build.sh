#!/bin/sh
# Build the frontend into frontend/dist (served by the backend at http://localhost:8000).
# Idempotent. Installs node modules only if they are missing. Does not restart anything:
# after a build, `make restart` bounces the launchd server, or just reload the dev server.
set -eu
cd "$(dirname "$0")"
[ -d frontend/node_modules ] || (cd frontend && npm install)
cd frontend && npm run build
