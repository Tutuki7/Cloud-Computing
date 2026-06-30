# Badges & Watchlist Microservices

Two independently deployable microservices — **Badges** and **Watchlists** — each exposing REST (FastAPI) and gRPC interfaces backed by PostgreSQL.

---

## Phase 5

Phase 5 adds Kubernetes deployment. The following changes were made:

- **`k8s/` directory** — new folder containing Kubernetes manifests:
  - `00-configmap.yaml` — general configuration (DB host/port/name, ...)
  - `01-secret.yaml` — sensitive values (DB password, DB connection URL)
  - `02-postgres.yaml` — PostgreSQL 15 Deployment + ClusterIP Service
  - `03-populate-db-phase5.yaml` — Kubernetes Job to populate the database
  - `12-badges-service.yaml` — Badges deployment + ClusterIP Service
  - `13-watchlists-service.yaml` — Watchlists deployment + ClusterIP Service
- Services are exposed internally  — no ports are exposed directly to the internet
- Docker images were published to Docker Hub.

---



## Running Locally
 ### 1. Download Required Files
 
The CSV files used to populate the database are too large to include in the repository and must be downloaded separately from Google Drive:
 
[Download data](https://drive.google.com/drive/folders/1yBRaUi72Y1QmUHmtBbip8_81QaxbVKey?usp=drive_link)
 
Once downloaded, place the `data` folder containing the CSV files at:
 
```
CC2526-Group8/db/data
```

### Environment Variables

Create a `.env` file in the project root:

```env
# Database configuration
DB_USER=db_user # should be a string
DB_PASSWORD=db_password # should be a string
DB_NAME=db_name # should be a string
DB_HOST=postgres
DB_PORT=db_port # should be an integer 
DB_URL=postgresql://db_user:db_password@db_host:db_port/db_name  
#----SERVICES-------
# Badges service
BADGE_SERVICE_PORTS=review_rest_port:review_rest_port # should be an integer
BADGE_GRPC_PORTS=review_grpc_port:review_grpc_port # should be an integer
BADGE_GRPC_PORT=review_grpc_port # should be an integer
BADGE_REST_PORT=review_rest_port # should be an integer
BADGE_REST_URL="http://badge-api:review_rest_port"
BADGE_GRPC_URL="badge-grpc:review_grpc_port"
# Watchlists service
WATCHLIST_SERVICE_PORTS=review_rest_port:review_rest_port # should be an integer
WATCHLIST_GRPC_PORTS=review_grpc_port:review_grpc_port # should be an integer
WATCHLIST_GRPC_PORT=review_grpc_port # should be an integer
WATCHLIST_REST_PORT=review_rest_port # should be an integer
WATCHLIST_REST_URL="http://watchlist-api:review_rest_port"
WATCHLIST_GRPC_URL="watchlist-grpc:review_grpc_port"
```

### Start Services

```bash
docker compose up --build -d
```

This starts:
- `postgres` — PostgreSQL 15 with schema from `db/init.sql`
- `populate-db` — seeds the database from CSV files in `db/data/` (if uncommented)
- `badge-grpc` — gRPC server for Badges
- `badge-api` — REST API for Badges
- `watchlist-grpc` — gRPC server for Watchlists
- `watchlist-api` — REST API for Watchlists

---

## Cloud Deployment

### Prerequisites

- A running cluster with `kubectl` configured to point at it
- A dedicated namespace created for this project:

```bash
kubectl create namespace group8
kubectl config set-context --current --namespace=group8
```

### Apply the Manifests

```bash
kubectl apply -f k8s/00-configmap.yaml
kubectl apply -f k8s/01-secret.yaml
kubectl apply -f k8s/02-postgres.yaml
```

Wait for PostgreSQL to finish:

```bash
kubectl wait --for=condition=Ready pod -l app=postgres --timeout=120s
```

Then run the database population jobs:

```bash
kubectl apply -f k8s/03-populate-db-phase5.yaml
```

Wait for the population to finish:

```bash
kubectl wait --for=condition=complete job/populate-db-phase5 --timeout=300s
```

Then deploy the microservices:

```bash
kubectl apply -f k8s/12-badges-service.yaml
kubectl apply -f k8s/13-watchlists-service.yaml
```

### Testing

To test locally while the pods are running:

```bash
# Users service
kubectl port-forward svc/users-service 8001:8001

# Movies service
kubectl port-forward svc/movies-service 8002:8002
```

---

## Services

| Service        | REST API                      | gRPC              |
|----------------|-------------------------------|-------------------|
| Badges Service   | http://localhost:8006         | localhost:50058   |
| Watchlists Service  | http://localhost:8007         | localhost:50059   |


Swagger UI (interactive API docs) is available at:

- **Badges Service:** http://localhost:8006/docs
- **Watchlists Service:** http://localhost:8007/docs

> Ports depend on the values defined in your `.env` file. The examples above use the defaults from `.env.example`.


---

## Badges Service

Manages badge definitions and awards them to users.

### REST API

Swagger UI: `http://localhost:8001/docs`

#### Badge Definitions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/badges` | List all badge definitions |
| `POST` | `/badges` | Create a new badge |
| `GET` | `/badges/{badge_id}` | Get a badge by ID |
| `PUT` | `/badges/{badge_id}` | Update a badge |
| `DELETE` | `/badges/{badge_id}` | Delete a badge |

#### User Badges

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/users/{user_id}/badges` | List badges awarded to a user |
| `POST` | `/users/{user_id}/badges` | Award a badge to a user |
| `GET` | `/users/{user_id}/badges/stream` | SSE stream of badge-award events |

#### Example Requests

```bash
# Create a badge
POST http://localhost:8001/badges
Content-Type: application/json

{
  "title": "First Review",
  "milestone": 10,
  "description": "Awarded after writing 10 reviews"
}

# Award a badge to a user
POST http://localhost:8001/users/42/badges
Content-Type: application/json

{
  "badge_id": 1
}

# Get all badges for a user
GET http://localhost:8001/users/42/badges

# Stream badge events (SSE)
GET http://localhost:8001/users/42/badges/stream
```

### gRPC Interface

Server listens on `0.0.0.0:50052`.

| Method | Description |
|--------|-------------|
| `ListBadges` | Returns all badge definitions |
| `GetBadge` | Returns a single badge by ID |
| `CreateBadge` | Creates a new badge; returns `ALREADY_EXISTS` if title is duplicate |
| `UpdateBadge` | Updates title, milestone, or description |
| `DeleteBadge` | Deletes a badge by ID |
| `GetUserBadges` | Returns all badges awarded to a user |
| `AwardBadge` | Awards a badge to a user; returns `ALREADY_EXISTS` if already held |

### Data Models

**Badge**
```
badge_id    int
title       string  (required, unique)
milestone   int     (required, ≥ 1)
description string
```

**UserBadge**
```
badge_id    int
user_id     string
awarded_at  Timestamp
badge       Badge
```

---

## Watchlist Service

Manages user-created watchlists and the movies within them.

### REST API

Swagger UI: `http://localhost:8002/docs`

#### Watchlists

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/watchlists` | List all watchlists |
| `POST` | `/watchlists` | Create a new watchlist |
| `GET` | `/watchlists/{watchlist_id}` | Get a watchlist and its movies |
| `PUT` | `/watchlists/{watchlist_id}` | Update a watchlist title |
| `DELETE` | `/watchlists/{watchlist_id}` | Delete a watchlist |
| `GET` | `/users/{user_id}/watchlist` | Get all watchlists for a user |

#### Watchlist Movies

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/watchlists/{watchlist_id}/movies` | Add a movie to a watchlist |
| `DELETE` | `/watchlists/{watchlist_id}/movies/{movie_id}` | Remove a movie from a watchlist |

#### Example Requests

```bash
# Create a watchlist
POST http://localhost:8002/watchlists
Content-Type: application/json

{
  "user_id": "42",
  "title": "My Favourites"
}

# Add a movie
POST http://localhost:8002/watchlists/1/movies
Content-Type: application/json

{
  "movie_id": 296
}

# Get user's watchlists
GET http://localhost:8002/users/42/watchlists

# Delete a watchlist
DELETE http://localhost:8002/watchlists/1
```

### gRPC Interface

Server listens on `0.0.0.0:50053`.

| Method | Description |
|--------|-------------|
| `ListWatchlists` | Returns all watchlists |
| `GetWatchlist` | Returns a watchlist and its movies |
| `CreateWatchlist` | Creates a watchlist for a user |
| `UpdateWatchlist` | Updates the watchlist title |
| `DeleteWatchlist` | Deletes a watchlist by ID |
| `GetUserWatchlists` | Returns all watchlists owned by a user |
| `AddMovieToWatchlist` | Adds a movie to a watchlist |
| `RemoveMovieFromWatchlist` | Removes a movie from a watchlist |
