# Microservices Deployment Guide (GKE) - Database per service + Monitoring

This document provides step-by-step instructions for deploying the project microservices on Google Kubernetes Engine (GKE), including Prometheus and Grafana monitoring.

---
---
---
## Notas para juntar tudo
1. No configmap podemos removo as linhas que definem os dados da DB porque a DP deixa de ser unica. Não deve causar problemas.
---
2. No secret o DB_URL passa a ser DB_USER. Não deve causar problemas.
---
3. Nos postgres são todos cópias uns dos outros, nada de novo
---
4. Nos populatedb também são todos cópias, as unicas imagens que existem para populates individuais são as minhas então é só usar essas. Usar a v1 é usar os CSV, usar a v2 é usar os DUMP.
---
5. Todos os services estão a ussar imagens minhas. Se quiserem criar imagens novas que misturem várias alterações e quiserem garantir que incluem as minhas mudanças principais, elas são:
- Todos exceto badges e watchlists é preciso no CONFIG.PY substituir o ```DB_URL = os.getenv("DB_URL")``` por
```bash
DB_URL = os.getenv("DB_URL") or (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)
```
- Nos badges e wathclists é a mesma alteração de cima mas no badges-server e watchlists-server. Also o main está desatualizado nestes meus serviços então talvez só dar merge neles porque ninguem mais deve ter mexido.
- Todos no DOCKERFILE é preciso adicionar ```RUN sed -i 's/\r//' start.sh``` e substituir ```CMD ["./start.sh"]``` por ```CMD ["/bin/sh", "/movies/start.sh"]```
- Todos no REQUIREMENTS.TXT adicionar ```prometheus-fastapi-instrumentator```
- Todos no ficheiro principal (movies.py,users.py,badges.py,etc...) adicionar no início ```from prometheus_fastapi_instrumentator import Instrumentator``` e na última linha ```Instrumentator().instrument(app).expose(app)```
- O movies e o reviews levaram alterações bastante profundas e reescrevi completamente o avg_rating então talvez aqui dar merge dos meus e fazer as alterações dos outros porque não me lembro do que fiz :\

---
6. No ingress substitui  ```path: /users-service``` por ```path: /users(/|$)(.*)``` (dependendo do nome do serviço) e ```pathType: Prefix``` por ```pathType: ImplementationSpecific```. Não deve causar problemas com nenhuma versão
---
7. Os últimos 3 Yamls são especificos a mim, é meter na pasta e alterar a numerção e rezar que não causem problemas com nenhuma das alterações novas.
---
---
---

## K8s File Reference

| File | Purpose |
|---|---|
| `00-configmap.yaml` | Shared environment variables for all services |
| `01-secret.yaml` | Database credentials and JWT secret |
| `02-postgres-*.yaml` (x7) | One PostgreSQL deployment per service |
| `03-populate-db-*.yaml` (x7) | Seed jobs to populate each database |
| `04–10 *-service.yaml` (x7) | Microservice deployments and ClusterIP services |
| `11-ingress.yaml` | NGINX ingress rules for all microservices |
| `12-monitoring-postgres.yaml` | Prometheus postgres_exporter for each database |
| `13-monitoring-bridge.yaml` | ExternalName bridge services + Grafana/Prometheus ingress rules |
| `14-monitoring-scrape.yaml` | Prometheus scrape config for the group8 namespace |

---

## 1. Cluster Setup

Ensure the Kubernetes Engine API is enabled, then create the cluster.

```bash
gcloud container clusters create group8-cluster \
    --zone europe-west1-b \
    --num-nodes 2 \
    --machine-type e2-standard-2 \
    --disk-type pd-standard \
    --disk-size 30 \
    --enable-ip-alias \
    --release-channel regular

gcloud container clusters get-credentials group8-cluster --zone europe-west1-b
```

---

## 2. Monitoring Stack Setup (Prometheus + Grafana)

Install Helm, then deploy the kube-prometheus-stack. This runs before the namespace and services.

```bash
# Linux / Cloud Shell
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Windows (PowerShell)
# winget install Helm.Helm  ← run this separately, then restart PowerShell

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --set grafana.adminPassword=yourpassword \
  --set prometheus.prometheusSpec.retention=7d \
  --set "grafana.grafana\.ini.server.root_url=%(protocol)s://%(domain)s/grafana" \
  --set "grafana.grafana\.ini.server.serve_from_sub_path=true" \
  --set "prometheus.prometheusSpec.routePrefix=/prometheus" \
  --set "prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false" \
  --set "prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false" \
  --set "prometheus.prometheusSpec.additionalScrapeConfigs[0].name=additional-scrape-configs" \
  --set "prometheus.prometheusSpec.additionalScrapeConfigs[0].key=prometheus-additional.yaml"
```

> **Note:** The external IP is not known at this point — `externalUrl` can be set later with `helm upgrade` once the ingress IP is available (step 8). Everything will still work without it.

---

## 3. Namespace and Environment Configuration

```bash
kubectl create namespace group8
kubectl config set-context --current --namespace=group8

kubectl apply -f k8s/00-configmap.yaml
kubectl apply -f k8s/01-secret.yaml
```

---

## 4. Database Deployment and Population

The PostgreSQL database for a service must be running and populated before that service will work.

```bash
# Deploy all databases
kubectl apply -f k8s/02-postgres-users.yaml
kubectl apply -f k8s/02-postgres-movies.yaml
kubectl apply -f k8s/02-postgres-ratings.yaml
kubectl apply -f k8s/02-postgres-recommendations.yaml
kubectl apply -f k8s/02-postgres-subscriptions.yaml
kubectl apply -f k8s/02-postgres-badges.yaml
kubectl apply -f k8s/02-postgres-watchlists.yaml

# Wait for all databases to be ready
kubectl wait --for=condition=ready pod -l app=postgres-users --timeout=120s
kubectl wait --for=condition=ready pod -l app=postgres-movies --timeout=120s
kubectl wait --for=condition=ready pod -l app=postgres-ratings --timeout=120s
kubectl wait --for=condition=ready pod -l app=postgres-recommendations --timeout=120s
kubectl wait --for=condition=ready pod -l app=postgres-subscriptions --timeout=120s
kubectl wait --for=condition=ready pod -l app=postgres-badges --timeout=120s
kubectl wait --for=condition=ready pod -l app=postgres-watchlists --timeout=120s

# Populate databases
kubectl apply -f k8s/03-populate-db-users.yaml
kubectl apply -f k8s/03-populate-db-movies.yaml
kubectl apply -f k8s/03-populate-db-ratings.yaml
kubectl apply -f k8s/03-populate-db-recommendations.yaml
kubectl apply -f k8s/03-populate-db-subscriptions.yaml
kubectl apply -f k8s/03-populate-db-badges.yaml
kubectl apply -f k8s/03-populate-db-watchlists.yaml

# Monitor jobs until all show 'Complete', then Ctrl+C
kubectl get jobs --watch
```

---

## 5. Microservices Deployment

```bash
kubectl apply -f k8s/04-users-service.yaml
kubectl apply -f k8s/05-movies-service.yaml
kubectl apply -f k8s/06-reviews-service.yaml
kubectl apply -f k8s/07-recommendations-service.yaml
kubectl apply -f k8s/08-badges-service.yaml
kubectl apply -f k8s/09-watchlists-service.yaml
kubectl apply -f k8s/10-subscriptions-service.yaml
```

> **Note:** If a pod enters `ErrImagePull`, ensure the image path in the YAML is correct. To restart a service: `kubectl delete -f <file>.yaml` then `kubectl apply -f <file>.yaml`.

---

## 6. Monitoring Exporters and Scrape Config

```bash
kubectl apply -f k8s/12-monitoring-postgres.yaml
kubectl apply -f k8s/13-monitoring-bridge.yaml
kubectl apply -f k8s/14-monitoring-scrape.yaml
```

---

## 7. Ingress Configuration

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.2/deploy/static/provider/cloud/deploy.yaml

kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s

kubectl apply -f k8s/11-ingress.yaml
```

---

## 8. Get External IP and Finalize Prometheus URL

```bash
kubectl get ingress group8-ingress
```

Once you have the IP, update Prometheus with its public URL:

```bash
helm upgrade monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set grafana.adminPassword=yourpassword \
  --set prometheus.prometheusSpec.retention=7d \
  --set "grafana.grafana\.ini.server.root_url=%(protocol)s://%(domain)s/grafana" \
  --set "grafana.grafana\.ini.server.serve_from_sub_path=true" \
  --set "prometheus.prometheusSpec.externalUrl=http://<EXTERNAL-IP>/prometheus" \
  --set "prometheus.prometheusSpec.routePrefix=/prometheus" \
  --set "prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false" \
  --set "prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false" \
  --set "prometheus.prometheusSpec.additionalScrapeConfigs[0].name=additional-scrape-configs" \
  --set "prometheus.prometheusSpec.additionalScrapeConfigs[0].key=prometheus-additional.yaml"
```

### Service Routing Table

| Service | Path | Internal Port |
|---|---|---|
| `users-service` | `/users` | 8001 |
| `movies-service` | `/movies` | 8002 |
| `review-service` | `/reviews` | 8003 |
| `recommendations-service` | `/recommendations` | 8004 |
| `subscriptions-service` | `/subscriptions` | 8005 |
| `badges-service` | `/badges` | 8006 |
| `watchlists-service` | `/watchlists` | 8007 |
| Grafana | `/grafana` | 80 |
| Prometheus | `/prometheus` | 9090 |

---

## 9. Using Prometheus

Access Prometheus at `http://<EXTERNAL-IP>/prometheus`.

### Check Scrape Targets

Go to `http://<EXTERNAL-IP>/prometheus/targets` — all services and postgres exporters should show **UP** under `scrapeConfig/monitoring/group8-services`.

### Example Queries

**Total HTTP requests across all services:**
```promql
http_requests_total{namespace="group8"}
```

**Request rate per service (last 5 minutes):**
```promql
rate(http_requests_total{namespace="group8"}[5m])
```

**Request rate for movies service only:**
```promql
rate(http_requests_total{pod=~"movies-service.*"}[5m])
```

**Error rate (4xx and 5xx) across all services:**
```promql
rate(http_requests_total{namespace="group8", status_code=~"4..|5.."}[5m])
```

**Average response latency per service:**
```promql
rate(http_request_duration_seconds_sum{namespace="group8"}[5m])
/
rate(http_request_duration_seconds_count{namespace="group8"}[5m])
```

**P95 latency for movies service:**
```promql
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{pod=~"movies-service.*"}[5m]))
```

**PostgreSQL active connections per database:**
```promql
pg_stat_activity_count{namespace="group8"}
```

**PostgreSQL database size in bytes:**
```promql
pg_database_size_bytes{namespace="group8"}
```

---

## 10. Using Grafana

Access Grafana at `http://<EXTERNAL-IP>/grafana`. Login: `admin / yourpassword`.

### Importing Community Dashboards

Go to **Dashboards → Import**, paste the ID, click **Load**, select **Prometheus** as the datasource, then **Import**.

| Dashboard | ID | Shows |
|---|---|---|
| Kubernetes Cluster Overview | `315` | Node CPU, memory, pod count |
| PostgreSQL Database | `9628` | Connections, query time, DB size |
| FastAPI Observability | `16110` | Request rate, latency, errors per endpoint |
| NGINX Ingress | `9614` | Ingress traffic and error rates |

### Exploring Your Service Metrics

1. Click **Explore** (compass icon) in the left sidebar
2. Select **Prometheus** as the datasource
3. Click **Metrics browser** and filter by `job="scrapeConfig/monitoring/group8-services"`
4. Enter any PromQL query from section 9

### Building a Custom Dashboard

1. Go to **Dashboards → New → New Dashboard**
2. Click **Add visualization**
3. Select **Prometheus** as the datasource
4. Enter a query, set a panel title, click **Apply**
5. Repeat for other panels, then **Save dashboard**

### Useful Panels to Build

**Request rate by service:**
```promql
sum by (pod) (rate(http_requests_total{namespace="group8"}[5m]))
```

**Error rate by service:**
```promql
sum by (pod) (rate(http_requests_total{namespace="group8", status_code=~"4..|5.."}[5m]))
```

**Latency heatmap for movies:**
```promql
rate(http_request_duration_seconds_bucket{pod=~"movies-service.*"}[5m])
```

**PostgreSQL connections per DB:**
```promql
pg_stat_activity_count{namespace="group8"}
```

---

## 11. Troubleshooting & Verification

```bash
# Check all pod statuses
kubectl get pods -n group8
kubectl get pods -n monitoring

# Check postgres exporters are running
kubectl get pods -n group8 | grep exporter

# Check ingress
kubectl get ingress group8-ingress
kubectl describe ingress group8-ingress

# Check services
kubectl get svc -n group8
kubectl get svc -n monitoring

# Describe a specific pod (useful for ErrImagePull or CrashLoopBackOff)
kubectl describe pod <pod-name> -n group8

# View logs for a service
kubectl logs deployment/movies-service -n group8

# View logs for a postgres exporter
kubectl logs deployment/postgres-exporter-movies -n group8
```