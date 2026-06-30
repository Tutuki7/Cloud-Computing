FROM python:3.12-slim

WORKDIR /badges

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -m grpc_tools.protoc \
      -I . \
      --python_out=. \
      --grpc_python_out=. \
      ./grpc_files/badges.proto

RUN sed -i 's/\r//' start.sh
RUN chmod +x start.sh

ENV REST_PORT=8006
ENV GRPC_PORT=50058

EXPOSE ${REST_PORT} ${GRPC_PORT}

CMD ["/bin/sh", "/badges/start.sh"]