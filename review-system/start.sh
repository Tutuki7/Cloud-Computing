#!/bin/sh
set -e

python -m grpc_files.review_system_server &
uvicorn ratings:app --host 0.0.0.0 --port $REST_PORT --workers 2
