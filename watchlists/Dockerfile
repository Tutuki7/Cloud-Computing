FROM python:3.12-slim

WORKDIR /watchlists

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Generate gRPC stubs from proto inside the grpc directory
RUN python -m grpc_tools.protoc \
      -I . \
      --python_out=. \
      --grpc_python_out=. \
      ./grpc_files/watchlists.proto

RUN sed -i 's/\r//' start.sh
RUN chmod +x start.sh

ENV REST_PORT=8007
ENV GRPC_PORT=50059

EXPOSE ${REST_PORT} ${GRPC_PORT}

CMD ["/bin/sh", "/watchlists/start.sh"]