# Deployment Guide — CC2526 Group 8

Full deployment on GKE including Keycloak, GCP Secret Manager, TLS, Network Policies, Vertex AI (Gemini 1.5 Flash), and Pub/Sub async review analysis.

---

## Part 1 — One-time GCP Setup
#### ANTES DE TUDO no configmap substituir project_id pelo project id de cada um
> Run these steps **once** per GCP project. If the cluster already exists and these resources are already set up, skip to Part 2.

### 1.1 — Authenticate and set project

```bash
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
export PROJECT_ID=$(gcloud config get-value project)
echo "Project: $PROJECT_ID"
```

### 1.2 — Enable GCP APIs

```bash
gcloud services enable \
  container.googleapis.com \
  secretmanager.googleapis.com \
  pubsub.googleapis.com \
  aiplatform.googleapis.com
```

### 1.3 — Create the GKE cluster

```bash
export PROJECT_ID=$(gcloud config get-value project)


gcloud container clusters create group8-cluster \
  --zone europe-west1-b \
  --num-nodes 3 \
  --machine-type e2-standard-2 \
  --disk-type pd-standard \
  --disk-size 30 \
  --enable-ip-alias \
  --workload-pool=${PROJECT_ID}.svc.id.goog \
  --enable-network-policy \
  --release-channel regular

gcloud container clusters get-credentials group8-cluster --zone europe-west1-b
```

### 1.4 — Enable GKE_METADATA on the node pool

Required for Workload Identity to work on pods:

```bash
gcloud container node-pools update default-pool \
  --cluster=group8-cluster \
  --zone=europe-west1-b \
  --workload-metadata=GKE_METADATA
```

### 1.5 — Create secrets in GCP Secret Manager
#### To avoid bugs do the guide from here in google cloud console

Create all secrets:
```bash
echo -n "cng8"                  | gcloud secrets create group8-db-user                 --data-file=-
echo -n "m8cloud"               | gcloud secrets create group8-db-password              --data-file=-
echo -n "YOUR_KEYCLOAK_SECRET"  | gcloud secrets create group8-keycloak-client-secret  --data-file=-
printf '%s' 'AdminPassword123!@%' | gcloud secrets create group8-admin-password         --data-file=-
```

> The Keycloak client secret can be any strong random string.

### 1.6 — Create the ESO GCP Service Account and grant secret access

```bash
export PROJECT_ID=$(gcloud config get-value project)

gcloud iam service-accounts create eso-sa --project=${PROJECT_ID}

for SECRET in group8-db-user group8-db-password group8-keycloak-client-secret group8-admin-password; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:eso-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```

### 1.7 — Configure Workload Identity for ESO

```bash
# Binding for ESO running in the external-secrets namespace
gcloud iam service-accounts add-iam-policy-binding \
  eso-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[external-secrets/external-secrets]"

# Binding for the eso-sa K8s ServiceAccount in the default namespace
gcloud iam service-accounts add-iam-policy-binding \
  eso-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[default/eso-sa]"
```

### 1.8 — Create the Vertex AI + Pub/Sub Service Account and key

`review-service`, `review-worker`, and `recommendations-service` use a JSON key
to authenticate with Pub/Sub and Vertex AI (Gemini 1.5 Flash). The key must be
present as `sa-key.json` in the root of the repository before running `deploy.sh`.

```bash
# Create the service account
gcloud iam service-accounts create review-intelligence-sa \
  --display-name="Review Intelligence SA" \
  --project=${PROJECT_ID}

SA_EMAIL="review-intelligence-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# Vertex AI access
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.serviceAgent"

# Pub/Sub access
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/pubsub.publisher"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/pubsub.subscriber"

# Required for API quota and usage
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/serviceusage.serviceUsageConsumer"

# Download the key — place it in the repo root
gcloud iam service-accounts keys create sa-key.json \
  --iam-account="${SA_EMAIL}"
```


### 1.9 — Create Pub/Sub topic and subscription

```bash
gcloud pubsub topics create review-created --project=${PROJECT_ID}

gcloud pubsub subscriptions create review-worker-sub \
  --topic=review-created \
  --ack-deadline=60 \
  --project=${PROJECT_ID}

  # Grant the SA explicit permission on the subscription itself
gcloud pubsub subscriptions add-iam-policy-binding review-worker-sub \
  --member="serviceAccount:review-intelligence-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/pubsub.subscriber"

# And on the topic for publishing
gcloud pubsub topics add-iam-policy-binding review-created \
  --member="serviceAccount:review-intelligence-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"

```

---

## Part 2 — Deploy the project

### Step 1 — Upload files to Cloud Shell

Open [Google Cloud Shell](https://console.cloud.google.com/) and upload the project:

1. Click the **three dots** menu in the top-right of Cloud Shell
2. Select **Upload** and upload the entire project folder

Or clone from GitHub:
```bash
git clone <repo-url>
cd CC2526-Group8
```


Expected structure:
```
~/CC2526-Group8/
├── deploy.sh
├── sa-key.json               ← required, do not commit to Git
└── k8s/
    ├── 00-configmap.yaml
    ├── 01-external-secret.yaml
    ├── 01-secret-store.yaml
    ├── 02-postgres-users.yaml
    ├── 02-postgres-movies.yaml
    ├── 02-postgres-ratings.yaml
    ├── 02-postgres-recommendations.yaml
    ├── 02-postgres-subscriptions.yaml
    ├── 02-postgres-badges.yaml
    ├── 02-postgres-watchlists.yaml
    ├── 03-populate-db-users.yaml
    ├── 03-populate-db-movies.yaml
    ├── 03-populate-db-ratings.yaml
    ├── 03-populate-db-recommendations.yaml
    ├── 03-populate-db-subscriptions.yaml
    ├── 03-populate-db-badges.yaml
    ├── 03-populate-db-watchlists.yaml
    ├── 04-users-service.yaml
    ├── 05-movies-service.yaml
    ├── 06-reviews-service.yaml
    ├── 07-review-worker.yaml
    ├── 08-recommendations-service.yaml
    ├── 09-badges-service.yaml
    ├── 10-subscriptions-service.yaml
    ├── 11-watchlists-service.yaml
    ├── 12-keycloak.yaml
    ├── 13-keycloak-setup-job.yaml
    ├── 14-network-policies.yaml
    ├── 15-cluster-issuer.yaml
    ├── 16-monitoring-postgres.yaml
    ├── 17-monitoring-bridge.yaml
    ├── 18-monitoring-scrape.yaml
    └── 19-ingress.yaml
```

### Step 2 — Run the deployment script

```bash
cd CC2526-Group8/
cp ~/sa-key.json .

chmod +x deploy.sh
./deploy.sh
```

The script runs the following steps automatically:

1. Connects kubectl to the GKE cluster
2. Cleans up any previous deployment
3. Installs **External Secrets Operator** via Helm
4. Creates the `eso-sa` ServiceAccount with Workload Identity annotation
5. Installs **NGINX Ingress Controller** via Helm
6. Installs **cert-manager** via Helm and applies the Let's Encrypt ClusterIssuer
7. Applies `SecretStore` and `ExternalSecret` — syncs 4 secrets from GCP Secret Manager
8. Creates `gcp-sa-secret` from `sa-key.json` for Vertex AI and Pub/Sub access
9. Applies the ConfigMap
10. Deploys all **7 PostgreSQL** databases and waits for them to be ready
11. Runs all **7 database population** jobs and waits for completion
12. Deploys **Keycloak** and waits for it to be ready
13. Deploys all **8 microservices** (including review-worker)
14. Runs the **Keycloak setup job** (realm `cc2526`, roles, client) and **admin-db-init** job
15. Applies **Network Policies** (default-deny + explicit allow per service)
16. Applies **Monitoring** exporters and scrape config
17. Detects the NGINX LoadBalancer IP and applies the **TLS Ingress** with `nip.io` hostname

---

## Part 3 — Accessing the project

### Service URLs (HTTPS via Ingress)

Get the NGINX IP:
```bash
kubectl get svc ingress-nginx-controller -n ingress-nginx
```

| Service | URL |
|---|---|
| Users | `https://<NGINX-IP>.nip.io/users-service/docs` |
| Movies | `https://<NGINX-IP>.nip.io/movies-service/docs` |
| Reviews | `https://<NGINX-IP>.nip.io/reviews-service/docs` |
| Recommendations | `https://<NGINX-IP>.nip.io/recommendations-service/docs` |
| Subscriptions | `https://<NGINX-IP>.nip.io/subscriptions-service/docs` |
| Badges | `https://<NGINX-IP>.nip.io/badges-service/docs` |
| Watchlists | `https://<NGINX-IP>.nip.io/watchlists-service/docs` |

> The TLS certificate is issued automatically by Let's Encrypt. It may take up to 1 minute after the first deploy.

### Authentication — obtaining an access token

Login is done directly against Keycloak. Port-forward it first:

```bash
kubectl port-forward svc/keycloak 8080:8080
```

Then request a token:
```bash
set +H
ADMIN_PASS=$(kubectl get secret group8-secret -o jsonpath='{.data.ADMIN_PASSWORD}' | base64 -d)
SECRET=$(kubectl get secret group8-secret -o jsonpath='{.data.KEYCLOAK_CLIENT_SECRET}' | base64 -d)

curl -X POST http://localhost:8080/realms/cc2526/protocol/openid-connect/token \
  --data-urlencode "grant_type=password" \
  --data-urlencode "client_id=users-service" \
  --data-urlencode "client_secret=$SECRET" \
  --data-urlencode "username=admin" \
  --data-urlencode "password=$ADMIN_PASS"
```


Use the returned `access_token` as `Authorization: Bearer <token>` on protected endpoints.

### Admin credentials

| Field | Value |
|---|---|
| username | `admin` |
| email | `admin@cc2526.com` |
| password | `AdminPassword123!@%` |
| is_admin | `true` |

### LLM-powered endpoints

**Explained recommendations (Vertex AI — synchronous):**
```bash
curl -H "Authorization: Bearer <token>" \
  https://<NGINX-IP>.nip.io/recommendations-service/recommendations/<user_id>/explained
```

**Submit a review (triggers async Pub/Sub analysis):**
```bash
curl -X POST https://<NGINX-IP>.nip.io/reviews-service/ratings \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "movie_id": 20, "rating": 4.5, "review": "Stunning visuals but flat acting."}'
# Returns 201 immediately — analysis happens in the background
```

**Review summary (reads from DB, no LLM call):**
```bash
curl -H "Authorization: Bearer <token>" \
  https://<NGINX-IP>.nip.io/reviews-service/movies/<movie_id>/review-summary
```

---

## Part 4 — Checking cluster state

```bash
# All pods
kubectl get pods

# All services
kubectl get svc

# External secrets sync status
kubectl get externalsecret
kubectl describe externalsecret group8-secret

# TLS certificate status
kubectl get certificate
kubectl describe certificate group8-tls

# Ingress
kubectl get ingress

# Logs per service
kubectl logs deployment/users-service
kubectl logs deployment/movies-service
kubectl logs deployment/review-service
kubectl logs deployment/review-worker
kubectl logs deployment/recommendations-service
kubectl logs deployment/badges-service
kubectl logs deployment/subscriptions-service
kubectl logs deployment/watchlists-service
kubectl logs statefulset/keycloak

# Setup job logs
kubectl logs job/keycloak-setup
kubectl logs job/admin-db-init

# Tail review-worker to confirm it is listening for Pub/Sub messages
kubectl logs -f deployment/review-worker
```

---

