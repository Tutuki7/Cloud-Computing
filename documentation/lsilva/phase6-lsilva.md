# Phase 6 – Non-Functional Requirements and Technical Architecture

**CC2526 – Group 8**

---

## 1. Introduction

This document describes the plan for the final implementation and deployment phase of the project. The current platform consists of several microservices — users, movies, reviews, recommendations, subscriptions, badges, and watchlists — deployed on GKE via Kubernetes, backed by a shared PostgreSQL database.

The improvements proposed in this phase focus on **Security**, addressing five concrete gaps in the current architecture:

1. **Authentication** — replace custom JWT logic with a managed Identity Provider (Keycloak)
2. **Secret Management** — move sensitive values out of the Git repository into GCP Secret Manager
3. **Network Policies** — restrict pod-to-pod communication to declared routes only
4. **TLS** — expose all services over HTTPS instead of plain HTTP
5. **Rate Limiting** — protect endpoints from abuse and denial-of-service attacks

---

## 2. Problem Statement

### 2.1 Custom Authentication

The current `users-service` implements authentication entirely from scratch:

- Passwords are hashed with **SHA-256** directly in application code — a fast-by-design algorithm unsuitable for password storage, vulnerable to brute-force attacks
- **JWT tokens** are created and validated using a shared `JWT_SECRET` stored in a Kubernetes Secret
- Sessions are stored in a `user_sessions` table in PostgreSQL
- Login, logout, and token verification are custom REST endpoints (`/auth`, `/auth/logout`, `/auth/verify`)

This mixes two distinct responsibilities in one service, is difficult to audit, and lacks built-in protections such as brute-force lockout or token revocation.

### 2.2 Secret Management

The file `k8s/01-secret.yaml` contains sensitive values committed to the Git repository:

```yaml
stringData:
  DB_PASSWORD: "m8cloud"
  DB_URL: "postgresql://cng8:m8cloud@postgres:5432/movielens25m"
  JWT_SECRET: "36f442b3efcdb29303..."
  ADMIN_PASSWORD: "AdminPassword123!@%"
```

Kubernetes Secrets are base64-encoded, not encrypted. Anyone with repository access can decode these values instantly, and there is no audit trail of who accessed them or when.

### 2.3 Unrestricted Internal Traffic

By default, Kubernetes allows all pods in a namespace to communicate freely with each other. If any pod is compromised, an attacker can freely reach the database, Keycloak, or any other internal service — there is nothing blocking lateral movement inside the cluster.

### 2.4 No TLS / Plain HTTP

All traffic between clients and the cluster currently goes over plain **HTTP**. This means tokens, credentials, and user data are transmitted unencrypted over the network, making them trivially interceptable.

### 2.5 No Rate Limiting

The API endpoints have no protection against repeated requests. A client can hammer any endpoint indefinitely — enabling brute-force attacks on the login flow, scraping of movie data, or simply overloading the services.

---

## 3. Proposed Improvements

### 3.1 Keycloak — Identity Provider (BaaS)

**Keycloak** is an open-source Identity Provider implementing OpenID Connect (OIDC) and OAuth 2.0. It will be deployed as a StatefulSet inside the GKE cluster and will take over all authentication responsibilities from `users-service`.

What Keycloak provides out of the box, without any custom code:

| Capability | Detail |
|---|---|
| Token issuance | OIDC-compliant JWTs signed with RS256 (asymmetric keys — no shared secret) |
| Password storage | bcrypt/PBKDF2 — not SHA-256 |
| Session management | Built-in refresh token rotation and revocation |
| RBAC | Realm roles (`user`, `admin`) embedded in token claims |
| Brute-force protection | Account lockout after configurable failed attempts |
| Token validation | Services validate via JWKS public key endpoint |
| Admin API | Full REST API for programmatic user and role management |

The `users-service` becomes a pure user-profile CRUD service. The `/auth`, `/auth/logout`, and `/auth/verify` endpoints are removed. Clients obtain tokens directly from Keycloak.

**Authentication flow after the change:**
```
Before:  Client → POST /auth (users-service) → JWT signed with shared secret
After:   Client → POST /realms/cc2526/protocol/openid-connect/token (Keycloak) → JWT signed with RS256
```

**Registration remains transparent to the client:**
```
Client → POST /users (users-service) → creates DB profile + calls Keycloak Admin API to register identity
```

### 3.2 GCP Secret Manager + External Secrets Operator

All sensitive values will be moved from the repository into **GCP Secret Manager**, a managed GCP service where secrets are encrypted at rest (AES-256), access-controlled by IAM, and fully audited.

The **External Secrets Operator (ESO)** will be deployed in the cluster. It watches `ExternalSecret` custom resources and automatically syncs the referenced values from GCP Secret Manager into Kubernetes Secrets. The repository will only contain references to secret names — never the values themselves. Access is granted via **GKE Workload Identity**, eliminating the need for any service account key file.

**Before vs After:**

| | Before | After |
|---|---|---|
| Where secrets live | `k8s/01-secret.yaml` in Git repo | GCP Secret Manager |
| Encoding | base64 (not encrypted) | AES-256 encrypted at rest |
| Access control | Anyone with repo access | GCP IAM roles |
| Audit trail | None | GCP Audit Logs |
| Rotation | Manual edit + redeploy | Update in GCP, ESO syncs automatically |

### 3.3 Kubernetes Network Policies

A set of `NetworkPolicy` resources will be applied to the `group8` namespace, acting as a pod-level firewall. Only explicitly declared traffic will be allowed — everything else is denied by default.

**Allowed traffic matrix:**

| Source | Destination | Port | Reason |
|---|---|---|---|
| users-service | postgres | 5432 | Database access |
| movies-service | postgres | 5432 | Database access |
| movies-service | users-service | 50053 | gRPC user validation |
| users-service | keycloak | 8080 | Token validation + Admin API |
| movies-service | keycloak | 8080 | Token validation via JWKS |
| ingress-nginx | users-service | 8001 | Incoming REST traffic |
| ingress-nginx | movies-service | 8002 | Incoming REST traffic |
| keycloak-setup (Job) | keycloak | 8080 | Initial realm configuration |

No application code changes are required — Network Policies are purely infrastructure-level Kubernetes resources.

### 3.4 TLS with cert-manager and Let's Encrypt

All external traffic will be served over **HTTPS** by provisioning a TLS certificate automatically via **cert-manager** and **Let's Encrypt**. cert-manager runs as a controller in the cluster, requests certificates from Let's Encrypt, and renews them automatically before expiry — no manual certificate management needed.

The NGINX Ingress is updated with a `tls` block pointing to the certificate secret, and an annotation to redirect all HTTP traffic to HTTPS.

**What this gives:**
- All tokens, credentials, and user data are encrypted in transit
- Certificate provisioning and renewal are fully automated
- Let's Encrypt certificates are free

### 3.5 Rate Limiting via NGINX Ingress

Rate limiting will be enforced at the ingress level using native **NGINX Ingress annotations** — no additional components needed. Limits are applied per client IP before requests even reach the services.

Two limits will be configured:
- **Requests per second (RPS)** — caps the sustained request rate per IP
- **Burst** — allows short spikes above the limit before throttling kicks in

Clients that exceed the limit receive a `429 Too Many Requests` response.

This protects against:
- Brute-force attacks on the Keycloak token endpoint
- Scraping of the movies catalogue
- Accidental or intentional service overload

---

## 4. Non-Functional Requirements

| ID | Requirement | Addressed by |
|---|---|---|
| NFR-01 | Passwords must be stored using a secure adaptive hashing algorithm, not SHA-256 | Keycloak |
| NFR-02 | Token signing must use asymmetric keys — no shared secrets between services | Keycloak |
| NFR-03 | Authentication logic must not be implemented in application code | Keycloak |
| NFR-04 | Sensitive values must not be stored in the Git repository | GCP Secret Manager + ESO |
| NFR-05 | Every access to a secret must be auditable | GCP Secret Manager |
| NFR-06 | Pod-to-pod communication must be restricted to declared routes only | Network Policies |
| NFR-07 | A compromised pod must not be able to reach services it does not need | Network Policies |
| NFR-08 | All external traffic must be encrypted in transit | TLS / cert-manager |
| NFR-09 | Endpoints must be protected against repeated requests and brute-force | Rate Limiting |

---

## 5. Deployment Plan

### Prerequisites
- GKE cluster created and `kubectl` connected to it
- `gcloud` CLI authenticated with the project
- `helm` installed locally
- NGINX Ingress Controller installed in the cluster
- A registered domain name pointed at the ingress external IP

> **Note on file numbering:** The new manifests `k8s/12-keycloak.yaml`, `k8s/13-keycloak-setup-job.yaml`, `k8s/14-network-policies.yaml`, and `k8s/15-cluster-issuer.yaml` are numbered to avoid conflicts with the existing group manifests (`k8s/04` through `k8s/11`).

---

### Step 1 — Create secrets in GCP Secret Manager

This must happen before any service is deployed, since all pods depend on the synced secrets to start.

```bash
# Enable the Secret Manager API
gcloud services enable secretmanager.googleapis.com

# Create the secrets
gcloud secrets create group8-db-url \
  --data-file=<(echo -n "postgresql://cng8:m8cloud@postgres:5432/movielens25m")

gcloud secrets create group8-keycloak-client-secret \
  --data-file=<(echo -n "<client-secret-generated-after-keycloak-setup>")

gcloud secrets create group8-admin-password \
  --data-file=<(echo -n "AdminPassword123!@%")

# Grant the GKE Workload Identity service account access
gcloud iam service-accounts create eso-sa --project=<project-id>

gcloud secrets add-iam-policy-binding group8-db-url \
  --member="serviceAccount:eso-sa@<project-id>.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# repeat the above for the other two secrets
```

---

### Step 2 — Install External Secrets Operator and sync secrets into the cluster

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  --namespace external-secrets --create-namespace

kubectl apply -f k8s/01-secret-store.yaml    # SecretStore pointing to GCP
kubectl apply -f k8s/01-external-secret.yaml  # ExternalSecret referencing the 3 secrets

# Wait for secrets to be synced before proceeding
kubectl wait --for=condition=Ready externalsecret/group8-secret --timeout=60s
kubectl get secret group8-secret -n group8   # verify values are present
```

---

### Step 3 — Deploy PostgreSQL and populate the database

```bash
kubectl apply -f k8s/02-postgres.yaml
kubectl wait --for=condition=Ready pod -l app=postgres --timeout=120s

kubectl apply -f k8s/03-populate-db.yaml
kubectl wait --for=condition=complete job/populate-db-phase5 --timeout=300s
kubectl logs job/populate-db-phase5   # verify successful population
```

---

### Step 4 — Deploy Keycloak

```bash
kubectl apply -f k8s/12-keycloak.yaml
kubectl wait --for=condition=Ready pod -l app=keycloak --timeout=180s
```

---

### Step 5 — Configure Keycloak realm, client and roles

```bash
kubectl apply -f k8s/13-keycloak-setup-job.yaml
kubectl wait --for=condition=complete job/keycloak-setup --timeout=120s
kubectl logs job/keycloak-setup   # verify realm, client and roles were created

# After the job completes, retrieve the generated client secret from Keycloak
# and update the corresponding GCP secret:
gcloud secrets versions add group8-keycloak-client-secret \
  --data-file=<(echo -n "<actual-client-secret-from-keycloak>")
```

---

### Step 6 — Install cert-manager and configure TLS

```bash
helm repo add jetstack https://charts.jetstack.io
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager --create-namespace \
  --set installCRDs=true

# Wait for cert-manager to be fully ready before applying the issuer
kubectl wait --for=condition=Available deployment/cert-manager \
  -n cert-manager --timeout=120s

kubectl apply -f k8s/15-cluster-issuer.yaml   # Let's Encrypt ClusterIssuer
```

---

### Step 7 — Deploy updated services and ingress (with TLS + rate limiting)

```bash
kubectl apply -f k8s/00-configmap.yaml
kubectl apply -f k8s/04-users-service.yaml
kubectl apply -f k8s/05-movies-service.yaml
kubectl apply -f k8s/11-ingress.yaml   # updated with TLS block + rate limiting annotations
```

At this point, cert-manager will automatically request a certificate from Let's Encrypt for the configured domain. This can take 1–2 minutes.

```bash
# Monitor certificate issuance
kubectl get certificate -n group8 --watch
```

---

### Step 8 — Apply Network Policies

Network Policies are applied last to avoid blocking any traffic during the setup steps above.

```bash
kubectl apply -f k8s/14-network-policies.yaml
kubectl get networkpolicy -n group8
```

---

### Step 9 — Verify end-to-end

```bash
# HTTPS health checks
curl https://<your-domain>/users/health
curl https://<your-domain>/movies/health

# Obtain token from Keycloak
curl -X POST https://<your-domain>/keycloak/realms/cc2526/protocol/openid-connect/token \
  -d "grant_type=password&client_id=users-service&username=testuser&password=..."

# Use token on movies-service
curl -H "Authorization: Bearer <token>" https://<your-domain>/movies

# Verify HTTP redirects to HTTPS
curl -I http://<your-domain>/movies   # expect 301 or 308

# Test rate limiting (expect 429 after sustained requests)
for i in {1..25}; do curl -o /dev/null -s -w "%{http_code}\n" https://<your-domain>/movies; done
```