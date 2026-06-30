# Deployment Guide — CC2526 Group 8 (Phase 6)

This guide covers the full deployment of the project on GKE, including the Phase 6 security improvements (Keycloak + GCP Secret Manager + TLS + Network Policies).

---

## Prerequisites

Install these tools **once** on your local machine (or use Google Cloud Shell, which already has everything):

| Tool | Installation |
|---|---|
| `gcloud` CLI | [cloud.google.com/sdk](https://cloud.google.com/sdk/docs/install) |
| `kubectl` | `gcloud components install kubectl` |
| `helm` | `brew install helm` / `choco install kubernetes-helm` |
| `docker` | Only needed if you change code and want to build new images |

Authenticate gcloud:

```bash
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
```

---

## Part 1 — One-time GCP Setup

> Run these steps **once** per GCP project. Start by setting your project ID as a variable — every command below uses it.

```bash
export PROJECT_ID=$(gcloud config get-value project)
echo "Project: $PROJECT_ID"   # confirm it's correct
```

### 1.1 — Enable GCP APIs

```bash
gcloud services enable container.googleapis.com secretmanager.googleapis.com
```

### 1.2 — Create the GKE cluster with Workload Identity and Network Policy

```bash
gcloud container clusters create group8-cluster \
  --zone europe-west1-b \
  --num-nodes 2 \
  --machine-type e2-standard-2 \
  --disk-type pd-standard \
  --disk-size 30 \
  --enable-ip-alias \
  --workload-pool=${PROJECT_ID}.svc.id.goog \
  --enable-network-policy \
  --release-channel regular

# Connect kubectl to the cluster
gcloud container clusters get-credentials group8-cluster --zone europe-west1-b
```

> **Important:** `--workload-pool` enables Workload Identity (required for External Secrets Operator to authenticate with GCP Secret Manager without static credentials). `--enable-network-policy` enables Calico for NetworkPolicy enforcement.

### 1.3 — Enable GKE_METADATA on the node pool

After cluster creation, update the node pool so that pods can use Workload Identity:

```bash
gcloud container node-pools update default-pool \
  --cluster=group8-cluster \
  --zone=europe-west1-b \
  --workload-metadata=GKE_METADATA
```

### 1.4 — Create secrets in GCP Secret Manager

```bash
# Database user
gcloud secrets create group8-db-user \
  --data-file=<(echo -n "cng8")

# Database password
gcloud secrets create group8-db-password \
  --data-file=<(echo -n "m8cloud")

# Keycloak client secret
gcloud secrets create group8-keycloak-client-secret \
  --data-file=<(echo -n "MyKeycloakSecret123!")

# Admin user password
printf '%s' 'AdminPassword123!@%' | \
  gcloud secrets create group8-admin-password --data-file=-
```

### 1.5 — Create the GCP Service Account and grant access to secrets

```bash
# Create the service account
gcloud iam service-accounts create eso-sa --project=${PROJECT_ID}

# Grant access to each secret
for SECRET in group8-db-user group8-db-password group8-keycloak-client-secret group8-admin-password; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:eso-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```

### 1.6 — Configure Workload Identity (link K8s SA to GCP SA)

```bash
# Binding for ESO in the external-secrets namespace
gcloud iam service-accounts add-iam-policy-binding \
  eso-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[external-secrets/external-secrets]"

# Binding for the SA in the default namespace
gcloud iam service-accounts add-iam-policy-binding \
  eso-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[default/eso-sa]"
```

---

## Part 2 — Deploy the project (repeat whenever needed)

### Step 1 — Open Cloud Shell and upload the files

Open [Google Cloud Shell](https://console.cloud.google.com/) and upload the project files:

1. Click the **three dots** in the top-right corner of Cloud Shell
2. Select **"Upload"**
3. Upload the `k8s/` folder with all yaml files and the `deploy.sh` script

Expected structure in Cloud Shell after upload:

```
~/CC2526-Group8/
├── deploy.sh
└── k8s/
    ├── 00-configmap.yaml
    ├── 01-secret-store.yaml
    ├── 01-external-secret.yaml
    ├── 02-postgres.yaml
    ├── 03-populate-db.yaml
    ├── 04-users-service.yaml
    ├── 05-movies-service.yaml
    ├── 11-ingress.yaml
    ├── 12-keycloak.yaml
    ├── 13-keycloak-setup-job.yaml
    ├── 14-network-policies.yaml
    └── 15-cluster-issuer.yaml
```

> **Alternative:** If the repository is on GitHub, you can clone it directly:
> ```bash
> git clone <repo-url>
> cd CC2526-Group8
> ```

### Step 2 — Run the deployment script

```bash
chmod +x deploy.sh
./deploy.sh
```

The script automatically runs the following steps:

1. Connects `kubectl` to the GKE cluster (`group8-cluster`, `europe-west1-b`)
2. Cleans up any previous deployment
3. Installs the **External Secrets Operator** via Helm (idempotent — skips if already installed)
4. Creates the `eso-sa` ServiceAccount in the `default` namespace with Workload Identity annotation
5. Installs the **NGINX Ingress Controller** via Helm (idempotent)
6. Installs **cert-manager** via Helm and applies the Let's Encrypt `ClusterIssuer` (idempotent)
7. Applies the `SecretStore` and `ExternalSecret` — syncs the 4 secrets from GCP Secret Manager into the cluster
8. Applies the `ConfigMap` with non-sensitive configuration
9. Deploys **PostgreSQL** and waits for it to be ready
10. Runs the **database population job** with MovieLens data
11. Deploys **Keycloak** (Identity Provider) and waits for it to be ready
12. Deploys **users-service** and **movies-service**
13. Runs the **Keycloak setup job** (creates realm `cc2526`, roles, and client) and the **admin user creation job**
14. Applies **Network Policies** (default-deny + explicit allow rules per service)
15. Detects the NGINX LoadBalancer IP and applies the **TLS Ingress** with `*.nip.io` hostnames

At the end, the script prints:

```
Swagger UIs (direct LoadBalancer):
  Users:  http://<users-IP>:8001/docs
  Movies: http://<movies-IP>:8002/docs

Swagger UIs (HTTPS via Ingress — cert may take ~1 min to issue):
  Users:  https://users.<NGINX-IP>.nip.io/docs
  Movies: https://movies.<NGINX-IP>.nip.io/docs

Admin credentials:
  username: admin
  password: AdminPassword123!@%
```

---

## Part 3 — Accessing the project

### Swagger UI (interactive API documentation)

#### Via HTTPS Ingress (recommended)

| Service | URL |
|---|---|
| Users Service | `https://users.<NGINX-IP>.nip.io/docs` |
| Movies Service | `https://movies.<NGINX-IP>.nip.io/docs` |

The TLS certificate is issued automatically by Let's Encrypt via cert-manager. It may take up to 1 minute after the first deploy.

To get the NGINX IP:

```bash
kubectl get svc ingress-nginx-controller -n ingress-nginx
```

#### Via direct LoadBalancer (alternative)

| Service | URL |
|---|---|
| Users Service | `http://<users-IP>:8001/docs` |
| Movies Service | `http://<movies-IP>:8002/docs` |

```bash
kubectl get svc users-service movies-service
```

### Authentication — obtaining an access token

Login is done directly against **Keycloak**, not the users-service.

**First, port-forward Keycloak to your local machine:**

```bash
kubectl port-forward svc/keycloak 8080:8080
```

**Then request a token:**

```bash
curl -s -X POST http://localhost:8080/realms/cc2526/protocol/openid-connect/token \
  --data-urlencode "grant_type=password" \
  --data-urlencode "client_id=users-service" \
  --data-urlencode "client_secret=MyKeycloakSecret123!" \
  --data-urlencode "username=admin" \
  --data-urlencode "password=AdminPassword123!@%"
```

> **Note:** Use `--data-urlencode` (not `-d`) to correctly handle special characters in the password (`!@%`).

The response includes an `access_token` JWT. Use it in the `Authorization: Bearer <token>` header on protected endpoints.

### Admin user (created automatically on deploy)

| Field | Value |
|---|---|
| username | `admin` |
| email | `admin@cc2526.com` |
| password | `AdminPassword123!@%` |
| is_admin | `true` |

---

## Part 4 — Checking cluster state

```bash
# List all pods
kubectl get pods

# List all services and external IPs
kubectl get svc

# Check secrets synced from GCP Secret Manager
kubectl get externalsecret
kubectl describe externalsecret group8-secret

# Check TLS certificate status
kubectl get certificate
kubectl describe certificate group8-tls

# Check NGINX Ingress
kubectl get ingress
kubectl get svc ingress-nginx-controller -n ingress-nginx

# View service logs
kubectl logs deployment/users-service
kubectl logs deployment/movies-service
kubectl logs deployment/keycloak

# View setup job logs
kubectl logs job/keycloak-setup
kubectl logs job/admin-db-init
kubectl logs job/populate-db-phase5
```

---

## Part 5 — Local development (without GKE)

To run locally with Docker Compose:

### 1. Copy the environment file

```bash
cp .env.example .env
```

Edit `.env` if needed (the default values already work).

### 2. Start the containers

```bash
docker compose up --build -d
```

This starts:
- **postgres** — PostgreSQL 15 with the initialisation data
- **populate-db** — populates the database with MovieLens data
- **keycloak** — Keycloak 24 Identity Provider (`:8080`)
- **keycloak-setup** — configures the realm, client, and roles (runs once and exits)
- **users-service** — REST API (`:8001`) and gRPC (`:50053`)
- **movies-service** — REST API (`:8002`) and gRPC (`:50054`)

### 3. Access locally

| Service | URL |
|---|---|
| Users Service | http://localhost:8001/docs |
| Movies Service | http://localhost:8002/docs |
| Keycloak Admin | http://localhost:8080/admin |

To obtain a token locally:

```bash
curl -s -X POST http://localhost:8080/realms/cc2526/protocol/openid-connect/token \
  --data-urlencode "grant_type=password" \
  --data-urlencode "client_id=users-service" \
  --data-urlencode "client_secret=MyKeycloakSecret123!" \
  --data-urlencode "username=admin" \
  --data-urlencode "password=AdminPassword123!@%"
```

### 4. Stop the containers

```bash
docker compose down       # stop containers
docker compose down -v    # stop + delete the database volume
```

---

## Kubernetes Manifests — Quick Reference

| File | Kind | Purpose |
|---|---|---|
| `k8s/00-configmap.yaml` | ConfigMap | Non-sensitive configuration (DB host, Keycloak URL, etc.) |
| `k8s/01-secret-store.yaml` | SecretStore (ESO) | Connects the cluster to GCP Secret Manager via Workload Identity |
| `k8s/01-external-secret.yaml` | ExternalSecret (ESO) | Defines the 4 secrets to sync from GCP Secret Manager |
| `k8s/02-postgres.yaml` | Deployment + Service | PostgreSQL 15 (internal ClusterIP) |
| `k8s/03-populate-db.yaml` | Job | Populates the database with MovieLens data |
| `k8s/04-users-service.yaml` | Deployment + Service | Users microservice (REST :8001, gRPC :50053, LoadBalancer) |
| `k8s/05-movies-service.yaml` | Deployment + Service | Movies microservice (REST :8002, gRPC :50054, LoadBalancer) |
| `k8s/11-ingress.yaml` | Ingress | TLS Ingress via NGINX — routes `users.*` and `movies.*` subdomains |
| `k8s/12-keycloak.yaml` | StatefulSet + Service | Keycloak 24 Identity Provider (internal ClusterIP) |
| `k8s/13-keycloak-setup-job.yaml` | 2x Job | Configures Keycloak realm/client/roles + inserts the admin user |
| `k8s/14-network-policies.yaml` | NetworkPolicy (×13) | Default-deny + explicit allow rules per service and namespace |
| `k8s/15-cluster-issuer.yaml` | ClusterIssuer | Let's Encrypt production issuer for cert-manager (HTTP-01 via NGINX) |

---

## Security Architecture (Phase 6)

```
Client
  │
  ├─ HTTPS ──► NGINX Ingress Controller (LoadBalancer)
  │              │  TLS terminated — cert issued by Let's Encrypt via cert-manager
  │              ├─ users.<IP>.nip.io  ──► users-service  (:8001)
  │              └─ movies.<IP>.nip.io ──► movies-service (:8002)
  │
  ├─ POST /realms/cc2526/protocol/openid-connect/token ──► Keycloak (:8080)  [port-forward]
  │                                                         └─ issues JWT (RS256)
  │
  ├─ GET/POST /users/**  ─────────────────────────────────► users-service (:8001)
  │                                                         └─ validates token via Keycloak JWKS
  │
  └─ GET/POST /movies/** ─────────────────────────────────► movies-service (:8002)
                                                            └─ validates token via Keycloak JWKS

Secrets:  GCP Secret Manager ──► External Secrets Operator (Workload Identity) ──► K8s Secret (group8-secret)
Network:  Default-deny NetworkPolicy + explicit allow rules (Calico on GKE)
```

### Implemented NFRs

| ID | Requirement | Solution | Status |
|---|---|---|---|
| NFR-01 | Passwords stored with secure adaptive hashing | Keycloak (bcrypt/PBKDF2) | ✅ Done |
| NFR-02 | Token signing with asymmetric keys (no shared secret) | Keycloak RS256 + JWKS | ✅ Done |
| NFR-03 | Auth logic not implemented in application code | Keycloak replaces custom JWT | ✅ Done |
| NFR-04 | Sensitive values not stored in the Git repository | GCP Secret Manager + ESO | ✅ Done |
| NFR-05 | Every secret access is auditable | GCP Audit Logs | ✅ Done |
| NFR-06 | Pod-to-pod communication restricted to declared routes | Kubernetes NetworkPolicy (Calico) | ✅ Done |
| NFR-07 | Compromised pod cannot reach unneeded services | Default-deny + explicit allow rules | ✅ Done |
| NFR-08 | All external traffic encrypted in transit | TLS via cert-manager + Let's Encrypt | ✅ Done |
| NFR-09 | Endpoints protected against repeated requests | Rate Limiting via NGINX annotations | ✅ Done |
