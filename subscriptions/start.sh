#!/bin/sh
set -e

python -u -m grpc_files.subscriptions_server &
uvicorn subscriptions:app --host 0.0.0.0 --port $REST_PORT