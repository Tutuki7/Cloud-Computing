#!/bin/sh
set -e

python -u -m grpc_files.watchlists_server &
uvicorn watchlists:app --host 0.0.0.0 --port $REST_PORT