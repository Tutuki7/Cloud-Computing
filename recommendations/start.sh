#!/bin/sh
set -e

python -m grpc_files.recomendations_server &
uvicorn recommendations:app --host 0.0.0.0 --port $REST_PORT