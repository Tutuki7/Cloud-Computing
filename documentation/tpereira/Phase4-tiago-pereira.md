# CC2526 - Group 8
Distributed movie platform built with microservices. Each service exposes a REST API and a gRPC interface, backed by a shared PostgreSQL database.

**Cloud Computing - Mário Calha - Group 8**  
**Tiago Pereira, Joana Carrasqueira, Tiago Pina, Leonor Silva**

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
