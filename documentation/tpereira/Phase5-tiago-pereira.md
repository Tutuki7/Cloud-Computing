# CC2526 - Group 8
Distributed movie platform built with microservices. Each service exposes a REST API and a gRPC interface, backed by a shared PostgreSQL database.

**Cloud Computing - Mário Calha - Group 8**  
**Tiago Pereira, Joana Carrasqueira, Tiago Pina, Leonor Silva**

---

## What's new in Phase 5

Phase 5 adds Kubernetes deployment support on top of the existing local Docker Compose setup. The following changes were made:

- **`k8s/` directory** — new folder containing all Kubernetes manifests:
  - `00-configmap.yaml` — non-sensitive configuration (DB host/port/name, admin username, token expiry, gRPC URLs)
  - `01-secret.yaml` — sensitive values (DB password, DB connection URL, JWT secret, admin password)
  - `02-postgres.yaml` — PostgreSQL 15 Deployment + ClusterIP Service, with a readiness probe to gate dependent workloads
  - `05-populate-db-subscriptions.yaml` — Kubernetes Job that seeds the subscriptions table
  - `11-subscriptions-service.yaml` — Subscriptions microservice Deployment + ClusterIP Service (REST :8005, gRPC :50057)
- Services are exposed internally via **ClusterIP** only — no ports are exposed directly to the internet without an Ingress/Gateway
- Environment is fully driven by ConfigMap and Secret references — no hardcoded values in the pod specs
- Docker images were built and published to Docker Hub for use in the Kubernetes manifests

---

## Local Deployment

### 1. Clone the repository

```bash
git clone <repository-url>
cd <repository-folder>
```

### 2. Download the CSV data files

The CSV files used to populate the database are hosted on Google Drive due to their size:

[Download CSV files](https://drive.google.com/drive/folders/1yBRaUi72Y1QmUHmtBbip8_81QaxbVKey?usp=drive_link)

Once downloaded, place the `data` folder in: `CC2526-Group8/db/data`

### 3. Create the `.env` file

Copy the provided example file and fill in the values:

```bash
cp .env.example .env
```

Then edit `.env` with your values. The `.env.example` file in the root of the project documents all required variables and their expected format.

### 4. Build and run

```bash
docker compose up --build -d
```

This will start the following containers:

- **postgres** — PostgreSQL 15 database, initialized with `db/init.sql`. Other containers only start after a successful health check.
- **populate-db** — Populates the database with the CSV data. Microservices only start after this completes successfully.
- **subscriptions-service** — Runs the Subscriptions Management REST API and gRPC server.

### Stopping the project

```bash
docker compose down
```

To also remove the database volume (full reset):

```bash
docker compose down -v
```

---

## Cloud Deployment

### Prerequisites

- A running GKE cluster with `kubectl` configured to point at it
- A dedicated namespace created for this project:

```bash
kubectl create namespace group8
kubectl config set-context --current --namespace=group8
```

### Apply the Manifests in Order

```bash
kubectl apply -f k8s/00-configmap.yaml
kubectl apply -f k8s/01-secret.yaml
kubectl apply -f k8s/02-postgres.yaml
```

Wait for PostgreSQL to become ready before continuing:

```bash
kubectl wait --for=condition=Ready pod -l app=postgres --timeout=120s
```

Then run the database population jobs:

```bash
kubectl apply -f k8s/03-populate-db-phase5.yaml
kubectl apply -f k8s/05-populate-db-users.yaml
```

Wait for both jobs to complete:

```bash
kubectl wait --for=condition=complete job/populate-db-phase5 --timeout=300s
kubectl wait --for=condition=complete job/populate-db-users --timeout=120s
```

Then deploy the microservices:

```bash
kubectl apply -f k8s/11-subscriptions-service.yaml
```

### Kubernetes Resources Overview

| Manifest | Kind | Purpose |
|---|---|---|
| `00-configmap.yaml` | ConfigMap | Non-sensitive app configuration |
| `01-secret.yaml` | Secret | Passwords, JWT secret, DB URL |
| `02-postgres.yaml` | Deployment + Service | PostgreSQL 15, internal only (ClusterIP) |
| `05-populate-db-subscriptions.yaml` | Job | Seeds the subscriptions table |
| `11-subscriptions-service.yaml` | Deployment + Service | Subscriptions microservice (REST :8005, gRPC :50057) |

### Network Exposure

All services are of type **ClusterIP** and are not directly reachable from outside the cluster. To access the REST APIs from outside, an Ingress or Kubernetes Gateway must be configured and pointed at `subscriptions-service:8005`.

To test locally while the pods are running, use port-forwarding:

```bash
# Subscriptions service
kubectl port-forward svc/subscriptions-service 8005:8005
```

### Verify Everything is Running

```bash
kubectl get pods
kubectl get services
kubectl get jobs
```

---

This repository contains two main components developed for the Cloud Computing project:

1. **Data Processing Notebook** (`Base_de_Dados_CC_Grupo8.ipynb`) — cleaning, transformation and preparation of MovieLens + IMDb datasets for all project tables
2. **Subscriptions Microservice** — FastAPI REST + gRPC with Docker, managing one-to-one user subscriptions

## Data Processing Notebook

The `Base_de_Dados_CC_Grupo8.ipynb` notebook handles the complete data preparation pipeline:

### Data Sources
- **MovieLens 25M**: movies.csv, ratings.csv, tags.csv, links.csv
- **IMDb Datasets**: title.basics.tsv.gz, title.ratings.tsv.gz, title.principals.tsv.gz, name.basics.tsv.gz

### Generated Tables
| Table | Description | Records |
|-------|-------------|---------|
| `users` | Users with demographic data | ~162k |
| `movies` | Movies enriched with IMDb | ~62k |
| `genres` | Unique genres | ~20 |
| `ratings` | Ratings with mock reviews | ~25M |
| `subscriptions` | One-to-one user subscriptions | ~500 |
| `watchlists` | User movie lists | ~300 |
| `userpreferences` | Genre preferences | ~800 |
| `userreferencemovies` | User reference movies | ~1.5k |

### Key Features
- Title normalization and IMDb data cleaning
- Cross-enrichment MovieLens ↔ IMDb via tconst
- Consistent timestamp/review/fraud alert generation
- Rating validation (1.0-5.0, 0.5 increments)
- Final CSV export to `output/`
- Automatic PostgreSQL SQL schema generation

**Result**: Clean CSVs and SQL schema ready for PostgreSQL import.

**Clean CSVs + Schema Download**: [Download CSV Files](https://drive.google.com/drive/folders/1yBRaUi72Y1QmUHmtBbip8_81QaxbVKey?usp=drive_link)

Place CSVs in `CC2526-Group8/data/` folder after download.

The notebook generates the clean CSVs used for PostgreSQL population. The last 3 cells serve as proof-of-concept that the CSV files were correctly generated and respected the schema. Data insertion was validated locally in PostgreSQL.

## Subscriptions Microservice

FastAPI REST + gRPC server, Dockerized, managing user-associated subscriptions (one-to-one).

### Features
- ✅ Backend business validation (paid tiers require dates)
- ✅ Parallel gRPC server with REST
- ✅ Unbuffered logs (`PYTHONUNBUFFERED=1`)
- ✅ Healthcheck endpoints
- ✅ Docker Compose ready

## How to Run

### 1. Environment (.env)
```env
# Database
DB_USER=cng8
DB_PASSWORD=m8cloud
DB_NAME=movielens25m
DB_HOST=postgres
DB_PORT=5444
DB_URL=postgresql://cng8:m8cloud@postgres:5432/movielens25m

# Subscriptions Service
SUBSCRIPTIONS_REST_PORT=8003
SUBSCRIPTIONS_GRPC_PORT=50053
SUBSCRIPTIONS_SERVICE_PORTS=8003:8003
SUBSCRIPTIONS_GRPC_PORTS=50053:50053
```

### 2. Build and start
```bash
docker compose up --build -d
```

### 3. Check logs
```bash
docker compose logs -f subscriptions-service
```
**Expected**:


### 4. Test REST API
Swagger UI: **http://localhost:8003/docs**

**POST 500 error fix** (user exists in users but not subscriptions):
```sql
SELECT setval(
  pg_get_serial_sequence('subscriptions', 'subscription_id'),
  COALESCE((SELECT MAX(subscription_id) FROM subscriptions), 0) + 1,
  false
);
```

### 5. Test gRPC
**Note**: gRPC doesn't work in browser. Use Python client or `grpcurl`.

## 🔌 REST API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Healthcheck |
| `POST` | `/users/{user_id}/subscription` | Create subscription |
| `GET` | `/users/{user_id}/subscription` | Get user subscription |
| `PUT` | `/users/{user_id}/subscription` | Update subscription |
| `DELETE` | `/users/{user_id}/subscription` | Delete subscription |

**Implemented Validations**:
- One-to-one: max 1 subscription per user
- Paid tiers: `start_date` + `end_date` required
- `end_date >= start_date`

## gRPC Interface

**Port**: `localhost:50053`

Main method implemented:


**Python client test**:
```python
import grpc
from subscriptions.grpc_files import subscriptions_pb2, subscriptions_pb2_grpc

with grpc.insecure_channel("localhost:50053") as channel:
    stub = subscriptions_pb2_grpc.SubscriptionServiceStub(channel)
    response = stub.GetUserSubscription(subscriptions_pb2.GetUserSubscriptionRequest(user_id=1))
    print(response)
```

## Validation Tests

1. **Container status**: `docker compose ps`
2. **Logs**: `docker compose logs -f subscriptions-service`
3. **REST**: `http://localhost:8003/docs`
4. **gRPC**: Python client or `grpcurl localhost:50053 subscriptions.SubscriptionService/GetUserSubscription`

## Example Subscription

```json
{
  "subscription_id": 1,
  "users_id": 121982,
  "type": "premium",
  "status": "active",
  "start_date": "2023-10-04",
  "end_date": "2024-07-26"
}
```

## Stopping the Project

```bash
docker compose down
```

**Full reset (remove DB volume)**:
```bash
docker compose down -v
```

---
