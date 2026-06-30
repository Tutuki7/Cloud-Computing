#!/bin/bash
# =============================================================================
# deploy.sh — Full deployment script for CC2526 Group 8
# Run this from the root of the repository in Google Cloud Shell.
# =============================================================================

set -e

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ID=$(gcloud config get-value project)
CLUSTER_NAME="group8-cluster"
CLUSTER_ZONE="europe-west1-b"
GCP_SA="eso-sa@${PROJECT_ID}.iam.gserviceaccount.com"

BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

step() { echo -e "\n${BLUE}==> $1${NC}"; }
ok()   { echo -e "${GREEN}✓ $1${NC}"; }
err()  { echo -e "${RED}✗ $1${NC}"; exit 1; }

# ---------------------------------------------------------------------------
# Step 1 — Connect kubectl to the cluster
# ---------------------------------------------------------------------------
step "Connecting to GKE cluster..."
gcloud container clusters get-credentials "$CLUSTER_NAME" \
  --zone "$CLUSTER_ZONE" --project "$PROJECT_ID"
ok "kubectl connected"

# ---------------------------------------------------------------------------
# Step 2 — Clean up previous deployment
# ---------------------------------------------------------------------------
step "Cleaning up previous deployment..."
kubectl delete all --all --ignore-not-found 2>/dev/null || true
kubectl delete pvc --all --ignore-not-found 2>/dev/null || true
kubectl delete externalsecret --all --ignore-not-found 2>/dev/null || true
kubectl delete secretstore --all --ignore-not-found 2>/dev/null || true
kubectl delete secret group8-secret --ignore-not-found 2>/dev/null || true
kubectl delete networkpolicy --all --ignore-not-found 2>/dev/null || true
ok "Cleanup done"

# ---------------------------------------------------------------------------
# Step 3 — Install External Secrets Operator (idempotent)
# ---------------------------------------------------------------------------
step "Installing External Secrets Operator..."
helm repo add external-secrets https://charts.external-secrets.io 2>/dev/null || true
helm repo update 2>/dev/null || true

if helm status external-secrets -n external-secrets &>/dev/null; then
  ok "ESO already installed, skipping"
else
  helm install external-secrets external-secrets/external-secrets \
    --namespace external-secrets --create-namespace
  ok "ESO installed"
fi

step "Waiting for ESO to be ready..."
kubectl wait --for=condition=Available deployment/external-secrets \
  -n external-secrets --timeout=120s
kubectl wait --for=condition=Available deployment/external-secrets-webhook \
  -n external-secrets --timeout=120s
kubectl wait --for=condition=Available deployment/external-secrets-cert-controller \
  -n external-secrets --timeout=120s
ok "ESO ready"

# ---------------------------------------------------------------------------
# Step 3a — Create Kubernetes ServiceAccount for Workload Identity
# ---------------------------------------------------------------------------
step "Creating eso-sa ServiceAccount in default namespace..."
if kubectl get serviceaccount eso-sa -n default &>/dev/null; then
  ok "ServiceAccount already exists, skipping"
else
  kubectl create serviceaccount eso-sa -n default
  kubectl annotate serviceaccount eso-sa -n default \
    iam.gke.io/gcp-service-account="$GCP_SA"
  ok "ServiceAccount created and annotated"
fi

# ---------------------------------------------------------------------------
# Step 3b — Install NGINX Ingress Controller (idempotent)
# ---------------------------------------------------------------------------
step "Installing NGINX Ingress Controller..."
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx 2>/dev/null || true
helm repo update 2>/dev/null || true

if helm status ingress-nginx -n ingress-nginx &>/dev/null; then
  ok "NGINX Ingress already installed, skipping"
else
  helm install ingress-nginx ingress-nginx/ingress-nginx \
    --namespace ingress-nginx --create-namespace
  ok "NGINX Ingress installed"
fi

kubectl wait --for=condition=Available deployment/ingress-nginx-controller \
  -n ingress-nginx --timeout=120s
ok "NGINX Ingress Controller ready"

# ---------------------------------------------------------------------------
# Step 3c — Install cert-manager (idempotent)
# ---------------------------------------------------------------------------
step "Installing cert-manager..."
helm repo add jetstack https://charts.jetstack.io 2>/dev/null || true
helm repo update 2>/dev/null || true

if helm status cert-manager -n cert-manager &>/dev/null; then
  ok "cert-manager already installed, skipping"
else
  helm install cert-manager jetstack/cert-manager \
    --namespace cert-manager --create-namespace \
    --set crds.enabled=true
  ok "cert-manager installed"
fi

kubectl wait --for=condition=Available deployment/cert-manager \
  -n cert-manager --timeout=120s
kubectl wait --for=condition=Available deployment/cert-manager-webhook \
  -n cert-manager --timeout=120s
ok "cert-manager ready"

step "Applying ClusterIssuer (Let's Encrypt)..."
kubectl apply -f k8s/15-cluster-issuer.yaml
ok "ClusterIssuer applied"

# ---------------------------------------------------------------------------
# Step 4 — Apply SecretStore and ExternalSecret
# ---------------------------------------------------------------------------
step "Applying SecretStore and ExternalSecret..."
kubectl delete secretstore group8-secret-store --ignore-not-found 2>/dev/null || true
sed "s/PLACEHOLDER_PROJECT_ID/${PROJECT_ID}/g; \
     s/PLACEHOLDER_CLUSTER_ZONE/${CLUSTER_ZONE}/g; \
     s/PLACEHOLDER_CLUSTER_NAME/${CLUSTER_NAME}/g" \
  k8s/01-secret-store.yaml | kubectl apply -f -
kubectl apply -f k8s/01-external-secret.yaml

step "Waiting for secrets to sync from GCP Secret Manager..."
for i in $(seq 1 24); do
  STATUS=$(kubectl get externalsecret group8-secret \
    -o jsonpath='{.status.conditions[0].reason}' 2>/dev/null || echo "")
  if [ "$STATUS" = "SecretSynced" ]; then
    ok "Secrets synced successfully"
    break
  fi
  echo "  Waiting... ($i/24)"
  sleep 5
done
if [ "$STATUS" != "SecretSynced" ]; then
  err "Secrets failed to sync. Check: kubectl describe externalsecret group8-secret"
fi

# ---------------------------------------------------------------------------
# Step 4a — Create gcp-sa-secret for Vertex AI + Pub/Sub access
# (used by review-service, review-worker, recommendations-service)
# ---------------------------------------------------------------------------
step "Creating gcp-sa-secret for Vertex AI and Pub/Sub access..."
if kubectl get secret gcp-sa-secret &>/dev/null; then
  ok "gcp-sa-secret already exists, skipping"
else
  if [ ! -f "sa-key.json" ]; then
    err "sa-key.json not found in current directory. See Part 1 step 1.8 of the guide to generate it."
  fi
  kubectl create secret generic gcp-sa-secret \
    --from-file=sa-key.json=sa-key.json
  ok "gcp-sa-secret created"
fi

# ---------------------------------------------------------------------------
# Step 5 — Apply ConfigMap
# ---------------------------------------------------------------------------
step "Applying ConfigMap..."
kubectl apply -f k8s/00-configmap.yaml
ok "ConfigMap applied"

# ---------------------------------------------------------------------------
# Step 6 — Deploy all PostgreSQL databases
# ---------------------------------------------------------------------------
step "Deploying PostgreSQL databases..."
kubectl apply -f k8s/02-postgres-users.yaml
kubectl apply -f k8s/02-postgres-movies.yaml
kubectl apply -f k8s/02-postgres-ratings.yaml
kubectl apply -f k8s/02-postgres-recommendations.yaml
kubectl apply -f k8s/02-postgres-subscriptions.yaml
kubectl apply -f k8s/02-postgres-badges.yaml
kubectl apply -f k8s/02-postgres-watchlists.yaml

step "Waiting for all databases to be ready..."
kubectl wait --for=condition=Ready pod -l app=postgres-users           --timeout=120s
kubectl wait --for=condition=Ready pod -l app=postgres-movies          --timeout=120s
kubectl wait --for=condition=Ready pod -l app=postgres-ratings         --timeout=120s
kubectl wait --for=condition=Ready pod -l app=postgres-recommendations --timeout=120s
kubectl wait --for=condition=Ready pod -l app=postgres-subscriptions   --timeout=120s
kubectl wait --for=condition=Ready pod -l app=postgres-badges          --timeout=120s
kubectl wait --for=condition=Ready pod -l app=postgres-watchlists      --timeout=120s
ok "All databases ready"

# ---------------------------------------------------------------------------
# Step 7 — Populate all databases
# ---------------------------------------------------------------------------
step "Populating databases..."
kubectl apply -f k8s/03-populate-db-users.yaml
kubectl apply -f k8s/03-populate-db-movies.yaml
kubectl apply -f k8s/03-populate-db-ratings.yaml
kubectl apply -f k8s/03-populate-db-recommendations.yaml
kubectl apply -f k8s/03-populate-db-subscriptions.yaml
kubectl apply -f k8s/03-populate-db-badges.yaml
kubectl apply -f k8s/03-populate-db-watchlists.yaml

step "Waiting for all populate jobs to complete..."
kubectl wait --for=condition=complete job/populate-db-users           --timeout=1800s
kubectl wait --for=condition=complete job/populate-db-movies          --timeout=1800s
kubectl wait --for=condition=complete job/populate-db-ratings         --timeout=1800s
kubectl wait --for=condition=complete job/populate-db-recommendations --timeout=1800s
kubectl wait --for=condition=complete job/populate-db-subscriptions   --timeout=1800s
kubectl wait --for=condition=complete job/populate-db-badges          --timeout=1800s
kubectl wait --for=condition=complete job/populate-db-watchlists      --timeout=1800s
ok "All databases populated"

# ---------------------------------------------------------------------------
# Step 8 — Deploy Keycloak
# ---------------------------------------------------------------------------
step "Deploying Keycloak..."
kubectl delete statefulset keycloak --ignore-not-found
kubectl delete pvc keycloak-data-keycloak-0 --ignore-not-found
kubectl apply -f k8s/12-keycloak.yaml
kubectl rollout status statefulset/keycloak --timeout=180s
ok "Keycloak ready"

# ---------------------------------------------------------------------------
# Step 9 — Deploy all microservices
# ---------------------------------------------------------------------------
step "Deploying all microservices..."
kubectl apply -f k8s/04-users-service.yaml
kubectl apply -f k8s/05-movies-service.yaml
kubectl apply -f k8s/06-reviews-service.yaml
kubectl apply -f k8s/07-review-worker.yaml
kubectl apply -f k8s/08-recommendations-service.yaml
kubectl apply -f k8s/09-badges-service.yaml
kubectl apply -f k8s/10-subscriptions-service.yaml
kubectl apply -f k8s/11-watchlists-service.yaml

step "Waiting for all microservices to be available..."
kubectl wait --for=condition=Available deployment/users-service           --timeout=120s
kubectl wait --for=condition=Available deployment/movies-service          --timeout=120s
kubectl wait --for=condition=Available deployment/review-service          --timeout=120s
kubectl wait --for=condition=Available deployment/review-worker           --timeout=120s
kubectl wait --for=condition=Available deployment/recommendations-service --timeout=120s
kubectl wait --for=condition=Available deployment/badges-service          --timeout=120s
kubectl wait --for=condition=Available deployment/subscriptions-service   --timeout=120s
kubectl wait --for=condition=Available deployment/watchlists-service      --timeout=120s
ok "All microservices deployed"

# ---------------------------------------------------------------------------
# Step 10 — Configure Keycloak and create admin user
# ---------------------------------------------------------------------------
step "Configuring Keycloak (realm, roles, client, admin user)..."
kubectl delete job keycloak-setup admin-db-init --ignore-not-found
kubectl apply -f k8s/13-keycloak-setup-job.yaml
kubectl wait --for=condition=complete job/keycloak-setup --timeout=180s
kubectl wait --for=condition=complete job/admin-db-init  --timeout=120s
ok "Keycloak configured and admin user created"

# ---------------------------------------------------------------------------
# Step 11 — Apply Network Policies
# ---------------------------------------------------------------------------
step "Applying Network Policies..."
kubectl apply -f k8s/14-network-policies.yaml -n default
ok "Network Policies applied"

# ---------------------------------------------------------------------------
# Step 11b — Install Prometheus + Grafana (kube-prometheus-stack)
# ---------------------------------------------------------------------------
step "Installing Prometheus + Grafana..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
helm repo update 2>/dev/null || true

if helm status monitoring -n monitoring &>/dev/null; then
  ok "Prometheus stack already installed, skipping"
else
  helm install monitoring prometheus-community/kube-prometheus-stack \
    --namespace monitoring \
    --create-namespace \
    --set grafana.adminPassword=yourpassword \
    --set prometheus.prometheusSpec.retention=7d \
    --set "grafana.grafana\.ini.server.domain=8089-cs-436951599759-default.cs-europe-west1-iuzs.cloudshell.dev" \
    --set "grafana.grafana\.ini.server.root_url=%(protocol)s://%(domain)s/" \
    --set "grafana.grafana\.ini.server.serve_from_sub_path=false" \
    --set "grafana.grafana\.ini.security.allow_embedding=true" \
    --set "grafana.grafana\.ini.security.cookie_samesite=disabled" \
    --set "grafana.grafana\.ini.security.csrf_trusted_origins=8089-cs-436951599759-default.cs-europe-west1-iuzs.cloudshell.dev" \
    --set "prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false" \
    --set "prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false" \
    --set "prometheus.prometheusSpec.additionalScrapeConfigsSecret.name=additional-scrape-configs" \
    --set "prometheus.prometheusSpec.additionalScrapeConfigsSecret.key=prometheus-additional.yaml" \
    --set "prometheus.prometheusSpec.additionalScrapeConfigsSecret.optional=true"
  ok "Prometheus stack installed"
fi

kubectl wait --for=condition=Available deployment/monitoring-grafana \
  -n monitoring --timeout=180s
kubectl wait --for=condition=Available deployment/monitoring-kube-prometheus-operator \
  -n monitoring --timeout=180s
ok "Prometheus + Grafana ready"

# ---------------------------------------------------------------------------
# Step 12 — Apply Monitoring
# ---------------------------------------------------------------------------
step "Applying monitoring exporters and scrape config..."
kubectl apply -f k8s/16-monitoring-postgres.yaml
kubectl apply -f k8s/17-monitoring-bridge.yaml
kubectl apply -f k8s/18-monitoring-scrape.yaml
ok "Monitoring applied"

# ---------------------------------------------------------------------------
# Step 13 — Apply TLS Ingress
# ---------------------------------------------------------------------------
step "Waiting for NGINX Ingress external IP..."
for i in $(seq 1 24); do
  NGINX_IP=$(kubectl get svc ingress-nginx-controller -n ingress-nginx \
    -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
  if [ -n "$NGINX_IP" ]; then
    break
  fi
  echo "  Still pending... ($i/24)"
  sleep 5
done

if [ -z "$NGINX_IP" ]; then
  echo "WARNING: NGINX IP still pending — Ingress not applied. Run manually later:"
  echo "  NGINX_IP=\$(kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}')"
  echo "  sed \"s/PLACEHOLDER_HOST/\${NGINX_IP}.nip.io/g\" k8s/19-ingress.yaml | kubectl apply -f -"
else
  NGINX_HOST="${NGINX_IP}.nip.io"
  ok "NGINX IP: ${NGINX_IP}"
  sed "s/PLACEHOLDER_HOST/${NGINX_HOST}/g" k8s/19-ingress.yaml | kubectl apply -f -
  ok "TLS Ingress applied — host: ${NGINX_HOST}"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Deployment complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

if [ -n "$NGINX_HOST" ]; then
  echo "Service URLs (HTTPS via Ingress — cert may take ~1 min to issue):"
  echo "  Users:           https://${NGINX_HOST}/users-service/docs"
  echo "  Movies:          https://${NGINX_HOST}/movies-service/docs"
  echo "  Reviews:         https://${NGINX_HOST}/reviews-service/docs"
  echo "  Recommendations: https://${NGINX_HOST}/recommendations-service/docs"
  echo "  Subscriptions:   https://${NGINX_HOST}/subscriptions-service/docs"
  echo "  Badges:          https://${NGINX_HOST}/badges-service/docs"
  echo "  Watchlists:      https://${NGINX_HOST}/watchlists-service/docs"
fi
echo ""
echo "To get a Keycloak token:"
echo "  kubectl port-forward svc/keycloak 8080:8080"
echo "  Then POST to http://localhost:8080/realms/cc2526/protocol/openid-connect/token"
echo ""
echo "Admin credentials:"
echo "  username: admin"
echo "  password: AdminPassword123!@%"
