# Microservices Deployment Guide (GKE)
This document provides step-by-step instructions for deploying the project microservices on Google Kubernetes Engine (GKE), as executed in the project shell.

## 1. Cluster Setup
First, ensure the Kubernetes Engine API is enabled and created the cluster.

```
# Create the GKE cluster
gcloud container clusters create group8-cluster \
    --zone europe-west1-b \
    --num-nodes 2 \
    --machine-type e2-standard-2 \
    --disk-type pd-standard \
    --disk-size 30 \
    --enable-ip-alias \
    --release-channel regular

# Get authentication credentials for kubectl
gcloud container clusters get-credentials group8-cluster --zone europe-west1-b
```

## 2. Namespace and Environment Configuration
We isolated our project within a dedicated namespace and apply shared configurations.

```
# Create and switch to the group8 namespace
kubectl create namespace group8
kubectl config set-context --current --namespace=group8

# Apply configuration and secrets
kubectl apply -f 00-configmap.yaml
kubectl apply -f 01-secret.yaml
```

## 3. Database Deployment and Population
The PostgreSQL database must be running before the microservices can connect.

```
# Deploy Postgres
kubectl apply -f 02-postgres.yaml

# Run the database population job
kubectl apply -f 03-populate-db.yaml

# Monitor the job until status is 'Complete'
kubectl get jobs --watch
```

## 4. Microservices Deployment
Deploy the core functional services.
```
kubectl apply -f 04-users-service.yaml
kubectl apply -f 05-movies-service.yaml
kubectl apply -f 06-reviews-service.yaml
kubectl apply -f 07-recommendations-service.yaml
kubectl apply -f 08-badges-service.yaml
kubectl apply -f 09-watchlists-service.yaml
kubectl apply -f 10-subscriptions-service.yaml
```

**Note:** If a pod enters `ErrImagePull`, ensure the image path in the YAML is correct. To restart a service, you can use `kubectl delete -f <file>.yaml` and then `kubectl apply -f <file>.yaml`.

## 5. Ingress Configuration
To expose the services to the internet, we used an NGINX Ingress Controller.

### Install NGINX Controller
```
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.2/deploy/static/provider/cloud/deploy.yaml

# Wait for the controller to be ready
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s
```

### Apply Ingress Rules:
```
kubectl apply -f 11-ingress.yaml
```

## 6. Accessing the Application
Once deployed, find your **External IP**:
```
kubectl get ingress group8-ingress
```

### Routing Table
The Ingress is configured to route traffic based on the following paths:

| **Service**               | **Internal Port** |
| ------------------------- | ----------------- |
| `users-service`           | 8001              |
| `movies-service`          | 8002              |
| `review-service`          | 8003              |
| `recommendations-service` | 8004              |
| `subscriptions-service`   | 8005              |
| `badges-service`          | 8006              |
| `watchlists-service`      | 8007              |

## 7. Troubleshooting & Verification
- **Check Pod Status:** `kubectl get pods`
- **Check Service Ports:** `kubectl get svc`
- **Describe Ingress:** `kubectl describe ingress group8-ingress`
- **Port Forwarding (Manual Test):** `kubectl port-forward service/review-service 8080:8003` (Access via web preview of cloud shell)
