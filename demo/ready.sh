#!/usr/bin/env bash
# From nothing to a demo that is ready to show — edtech-kg#25.
#
# A demo that begins with a load begins with ten minutes of nothing. This
# starts an engine, imports the published snapshot, and CHECKS THE GRAPH
# BEFORE SAYING IT IS READY — measured at well under a second against a load
# of about eight.
#
# It does not build the graph. The snapshot is a release asset, not source:
# `data/` is gitignored, and a graph artefact does not belong in a repository
# of the code that produces it.
#
#   ./demo/ready.sh                       # downloads nothing; expects the file
#   SNAPSHOT=~/Downloads/edtech-kg.sgsnap ./demo/ready.sh
#
set -euo pipefail

PORT="${PORT:-8200}"
URL="http://localhost:${PORT}"
SNAPSHOT="${SNAPSHOT:-data/edtech-kg.sgsnap}"
IMAGE="public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0"
NAME="${NAME:-edtech-demo}"

# **A Python this repo supports, not whatever `python3` resolves to.**
# `pyproject.toml` declares >=3.11 and `etl/provenance.py` imports `tomllib`,
# which arrived in 3.11 — on macOS `python3` is often Xcode's 3.9, and the
# failure lands as a ModuleNotFoundError three imports deep, which reads as a
# broken repo rather than as the wrong interpreter.
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && \
       "$candidate" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null; then
      PY="$candidate"; break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "no Python 3.11 or newer on PATH; set PYTHON=/path/to/python" >&2
  exit 2
fi

if [ ! -f "$SNAPSHOT" ]; then
  echo "no snapshot at $SNAPSHOT" >&2
  echo "Download edtech-kg.sgsnap from the Releases page, or produce one:" >&2
  echo "  python -m etl.snapshot export --url <a loaded engine>" >&2
  exit 2
fi

echo "starting a fresh engine on :${PORT}"
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -p "${PORT}:8080" "$IMAGE" >/dev/null

# Polled, not slept. A fixed sleep is a guess that is either wasteful or too
# short, and too short here means importing into an engine that is not up.
for _ in $(seq 1 60); do
  if curl -fsS "${URL}/api/tenants" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS "${URL}/api/tenants" >/dev/null 2>&1 || {
  echo "engine never answered on :${PORT}" >&2; docker logs "$NAME"; exit 1; }

"$PY" -m etl.snapshot import --url "$URL" --file "$SNAPSHOT"

# **The gate.** `import` reports what it imported; this asks the graph what it
# HOLDS, against the counts the record says a good snapshot produces. A demo
# that opens on a half-imported graph is worse than one that does not open.
"$PY" -m etl.snapshot verify --url "$URL"

echo
echo "ready. run the walkthrough with:"
echo "  SAMYAMA_URL=${URL} $PY -m demo.demo"
