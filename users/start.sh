#!/bin/sh
set -e
python -u -m grpc_files.users_server &
uvicorn users:app --host 0.0.0.0 --port $REST_PORT