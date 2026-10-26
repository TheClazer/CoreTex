#!/bin/sh
# Single-container entrypoint: runs the RQ worker and the API together.
#
# Used on hosts where a separate background-worker service isn't free
# (e.g. Render's free tier). The worker runs in a restart loop in the
# background; uvicorn runs in the foreground on $PORT so the platform's
# health checks and lifecycle track the API process.

(
  while true; do
    python -m app.queue.worker
    echo "worker exited; restarting in 3s" >&2
    sleep 3
  done
) &

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
