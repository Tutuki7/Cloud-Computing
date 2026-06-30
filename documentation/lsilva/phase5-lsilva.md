# CC2526 - Group 8

Distributed movie platform built with microservices. Each service exposes a REST API and a gRPC interface, backed by a shared PostgreSQL database.

---

## What's new in Phase 5

Phase 5 adds Kubernetes deployment support on top of the existing local Docker Compose setup. The following changes were made:

- **`k8s/` directory** — new folder containing all Kubernetes manifests:
  - `00-configmap.yaml` — non-sensitive configuration (DB host/port/name, admin username, token expiry, gRPC URLs)
  - `01-secret.yaml` — sensitive values (DB password, DB connection URL, JWT secret, admin password)
  - `02-postgres.yaml` — PostgreSQL 15 Deployment + ClusterIP Service, with a readiness probe to gate dependent workloads
  - `04-populate-db-users.yaml` — Kubernetes Job that seeds the users and movies tables and creates the admin account
  - `07-users-service.yaml` — Users microservice Deployment + ClusterIP Service (REST :8001, gRPC :50053)
  - `08-movies-service.yaml` — Movies microservice Deployment + ClusterIP Service (REST :8002, gRPC :50054)
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

> **Note:** An admin user is automatically created on startup using the `ADMIN_USERNAME`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` variables. No manual setup is required.

### 4. Build and run

```bash
docker compose up --build -d
```

This will start the following containers:

- **postgres** — PostgreSQL 15 database, initialized with `db/init.sql`. Other containers only start after a successful health check.
- **populate-db** — Populates the database with the CSV data and creates the admin user. Microservices only start after this completes successfully.
- **users-service** — Runs the User Management REST API and gRPC server.
- **movies-service** — Runs the Movie Catalog REST API and gRPC server.

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
kubectl apply -f k8s/04-populate-db-users.yaml
```

Wait for both jobs to complete:

```bash
kubectl wait --for=condition=complete job/populate-db-phase5 --timeout=300s
kubectl wait --for=condition=complete job/populate-db-users --timeout=120s
```

Then deploy the microservices:

```bash
kubectl apply -f k8s/07-users-service.yaml
kubectl apply -f k8s/08-movies-service.yaml
```

### Kubernetes Resources Overview

| Manifest | Kind | Purpose |
|---|---|---|
| `00-configmap.yaml` | ConfigMap | Non-sensitive app configuration |
| `01-secret.yaml` | Secret | Passwords, JWT secret, DB URL |
| `02-postgres.yaml` | Deployment + Service | PostgreSQL 15, internal only (ClusterIP) |
| `04-populate-db-users.yaml` | Job | Seeds users, movies, genres, cast data and creates admin account |
| `07-users-service.yaml` | Deployment + Service | Users microservice (REST :8001, gRPC :50053) |
| `08-movies-service.yaml` | Deployment + Service | Movies microservice (REST :8002, gRPC :50054) |

### Network Exposure

All services are of type **ClusterIP** and are not directly reachable from outside the cluster. To access the REST APIs from outside, an Ingress or Kubernetes Gateway must be configured and pointed at `users-service:8001` and `movies-service:8002`.

To test locally while the pods are running, use port-forwarding:

```bash
# Users service
kubectl port-forward svc/users-service 8001:8001

# Movies service
kubectl port-forward svc/movies-service 8002:8002
```

### Verify Everything is Running

```bash
kubectl get pods
kubectl get services
kubectl get jobs
```

---

## Services

| Service        | REST API                      | gRPC              |
|----------------|-------------------------------|-------------------|
| User Service   | http://localhost:8001         | localhost:50053   |
| Movie Service  | http://localhost:8002         | localhost:50054   |

> Ports depend on the values defined in your `.env` file. The examples above use the defaults from `.env.example`.

Swagger UI (interactive API docs) is available at:

- **User Service:** http://localhost:{USER_REST_PORT}/docs
- **Movie Service:** http://localhost:{MOVIE_REST_PORT}/docs

---

## Admin Access

An admin account is created automatically on first run using the credentials defined in the `.env` file. To authenticate, call the `/auth` endpoint on the User Service:

```http
POST http://localhost:{USER_REST_PORT}/auth
Content-Type: application/json

{
  "username": "<ADMIN_USERNAME>",
  "password": "<ADMIN_PASSWORD>"
}
```

Use the returned `access_token` as a Bearer token for all admin-only endpoints (creating, updating, or deleting movies, managing cast, promoting users to admin).

---

## User Service — REST API

### Users

| Method   | Endpoint                  | Auth     | Description                        |
|----------|---------------------------|----------|------------------------------------|
| GET      | /users                    | ❌        | List users (with optional filters) |
| POST     | /users                    | ❌        | Register a new user                |
| GET      | /users/{user_id}          | ❌        | Get a user by ID                   |
| PUT      | /users/{user_id}          | ✅ User   | Update user profile                |
| DELETE   | /users/{user_id}          | ✅ User   | Delete user account                |
| PATCH    | /users/{user_id}/admin    | ✅ Admin  | Promote or revoke admin role       |

### Authentication

| Method   | Endpoint         | Auth     | Description                              |
|----------|------------------|----------|------------------------------------------|
| POST     | /auth            | ❌        | Login and get access + refresh tokens    |
| POST     | /auth/logout     | ✅ User   | Invalidate all active sessions           |
| GET      | /auth/verify     | ✅ User   | Verify if a token is valid               |

### Postman Examples

**Register a user**
```http
POST http://localhost:{USER_REST_PORT}/users
Content-Type: application/json

{
  "username": "johndoe",
  "email": "john@example.com",
  "password": "SecurePassword123!",
  "gender": "M",
  "age": 25,
  "termsAccepted": true
}
```

**Login**
```http
POST http://localhost:{USER_REST_PORT}/auth
Content-Type: application/json

{
  "username": "johndoe",
  "password": "SecurePassword123!"
}
```

**Update user**
```http
PUT http://localhost:{USER_REST_PORT}/users/1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "username": "newusername",
  "age": 30
}
```

**Promote user to admin**
```http
PATCH http://localhost:{USER_REST_PORT}/users/2/admin?is_admin=true
Authorization: Bearer <admin_access_token>
```

### gRPC

| Method        | Description                  |
|---------------|------------------------------|
| GetUser       | Get a user by ID             |
| ValidateUser  | Check if a user exists       |

To test gRPC, run inside the container:
```bash
docker exec -it users-service python -c "
import grpc, sys
sys.path.insert(0, '/users/grpc')
import users_pb2, users_pb2_grpc

channel = grpc.insecure_channel('localhost:50053')
stub = users_pb2_grpc.UserServiceStub(channel)

r = stub.GetUser(users_pb2.GetUserRequest(user_id=1))
print(r)
"
```

---

## Movie Service — REST API

### Movies

| Method   | Endpoint              | Auth     | Description                          |
|----------|-----------------------|----------|--------------------------------------|
| GET      | /movies               | ❌        | List movies (with optional filters)  |
| POST     | /movies               | ✅ Admin  | Create a new movie                   |
| GET      | /movies/{movie_id}    | ❌        | Get a movie by ID                    |
| PUT      | /movies/{movie_id}    | ✅ Admin  | Update a movie                       |
| DELETE   | /movies/{movie_id}    | ✅ Admin  | Soft delete a movie                  |

### Genres

| Method   | Endpoint   | Auth | Description               |
|----------|------------|------|---------------------------|
| GET      | /genres    | ❌    | List all available genres |

### Cast

| Method   | Endpoint                            | Auth     | Description                  |
|----------|-------------------------------------|----------|------------------------------|
| GET      | /movies/{movie_id}/cast             | ❌        | Get cast of a movie          |
| POST     | /movies/{movie_id}/cast             | ✅ Admin  | Add a cast member to a movie |
| DELETE   | /movies/{movie_id}/cast/{cast_id}   | ✅ Admin  | Remove a cast member         |

### Postman Examples

**List movies with filters**
```http
GET http://localhost:{MOVIE_REST_PORT}/movies?title=toy&genre=Animation&release_year=1995&limit=10&offset=0
```

**Get a movie**
```http
GET http://localhost:{MOVIE_REST_PORT}/movies/1
```

**Create a movie**
```http
POST http://localhost:{MOVIE_REST_PORT}/movies
Authorization: Bearer <admin_access_token>
Content-Type: application/json

{
  "movie_title": "Inception",
  "description": "A thief who steals corporate secrets through dream-sharing technology.",
  "imdb_url": "https://www.imdb.com/title/tt1375666/",
  "release_year": 2010,
  "runtime": 148,
  "parental_rating": "PG-13",
  "poster_url": "https://example.com/inception.jpg",
  "genres": ["Action", "Sci-Fi", "Thriller"]
}
```

**Update a movie**
```http
PUT http://localhost:{MOVIE_REST_PORT}/movies/1
Authorization: Bearer <admin_access_token>
Content-Type: application/json

{
  "movie_title": "Toy Story (1995)",
  "parental_rating": "G"
}
```

**Delete a movie**
```http
DELETE http://localhost:{MOVIE_REST_PORT}/movies/1
Authorization: Bearer <admin_access_token>
```

**Add a cast member**
```http
POST http://localhost:{MOVIE_REST_PORT}/movies/1/cast
Authorization: Bearer <admin_access_token>
Content-Type: application/json

{
  "cast_name": "Tom Hanks",
  "role": "Woody"
}
```

### gRPC

| Method            | Description                              |
|-------------------|------------------------------------------|
| GetMovie          | Get a movie by ID                        |
| ValidateMovie     | Check if a movie exists                  |
| SearchMovies      | Search movies by title, genre, year      |
| GetMoviesBatch    | Get multiple movies by a list of IDs     |
| GetGenres         | List all available genres                |

To test gRPC, run inside the container:
```bash
docker exec -it movies-service python -c "
import grpc, sys
sys.path.insert(0, '/movies/grpc')
import movies_pb2, movies_pb2_grpc

channel = grpc.insecure_channel('localhost:50054')
stub = movies_pb2_grpc.MovieServiceStub(channel)

r = stub.GetMovie(movies_pb2.GetMovieRequest(movie_id=1))
print(r)
"
```