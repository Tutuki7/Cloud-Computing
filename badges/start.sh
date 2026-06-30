#!/bin/sh
set -e

python -u -m grpc_files.badges_server &
uvicorn badges:app --host 0.0.0.0 --port $REST_PORT