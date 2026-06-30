#!/bin/sh
set -e
 
echo "Starting gRPC server on port 50054..."
PYTHONPATH=/movies python /movies/grpc/movies_server.py &
 
echo "Starting REST API on port 8002..."
uvicorn movies:app --host 0.0.0.0 --port 8002