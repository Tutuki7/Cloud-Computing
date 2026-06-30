# Deployment Guide — CC2526 Group 8

Full deployment on GKE using **Terraform** for infrastructure and **Ansible** for Kubernetes setup, including Keycloak, GCP Secret Manager, TLS, Network Policies, Vertex AI (Gemini 1.5 Flash), and Pub/Sub async review analysis.

### Part 0 — Upload the project to Cloud Shell

Open [Google Cloud Shell](https://console.cloud.google.com/) and upload the entire `CC2526-Group8` folder before starting the deployment. This is required because the `Terraform/` folder is needed for the cluster setup in Part 1, the `Ansible/` folder is needed for the Kubernetes deployment in Part 2, and the `k8s/` folder contains the manifests applied by Ansible.

## Part 1 — One-time GCP setup

Before everything else, replace `project_id` in the ConfigMap and any environment-specific values with your own GCP Project ID. Use a **Project ID**, not a project number.

Run these steps once per GCP project. If the infrastructure already exists and the secrets are already set up, skip to Part 2.

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


### 1.3 — Create the GKE cluster with Terraform

Go to the Terraform folder inside `CC2526-Group8` and create the cluster there. Terraform is now responsible for the GKE setup, so this replaces the old manual `gcloud container clusters create` step.

```bash
cd ~/CC2526-Group8/Terraform
terraform init
terraform validate
terraform plan
terraform apply
```

If your Terraform code uses variables, make sure `terraform.tfvars` has the correct `project_id`, `region`, `zone`, and cluster name before applying.

After Terraform finishes, fetch credentials for the cluster.

```bash
gcloud container clusters get-credentials group8-cluster --zone europe-west1-b --project "$PROJECT_ID"
```


### 1.4 — Enable GKE metadata mode on the node pool

This is required for Workload Identity on pods.

```bash
gcloud container node-pools update primary-node-pool \
  --cluster=group8-cluster \
  --zone=europe-west1-b \
  --workload-metadata=GKE_METADATA
```


### 1.5 — Create secrets in GCP Secret Manager

To avoid bugs, do this part in Google Cloud Shell or directly in the Google Cloud Console.

Create all secrets:

```bash
echo -n "cng8"                   | gcloud secrets create group8-db-user                --data-file=-
echo -n "m8cloud"                | gcloud secrets create group8-db-password             --data-file=-
echo -n "MyKeycloakSecret123!"   | gcloud secrets create group8-keycloak-client-secret  --data-file=-
printf '%s' 'AdminPassword123!@%' | gcloud secrets create group8-admin-password         --data-file=-
```

The Keycloak client secret can be any strong random string.

### 1.6 — Create the ESO GCP service account and grant secret access

```bash
export PROJECT_ID=$(gcloud config get-value project)

gcloud iam service-accounts create eso-sa --project="${PROJECT_ID}"

for SECRET in group8-db-user group8-db-password group8-keycloak-client-secret group8-admin-password; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --member="serviceAccount:eso-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```


### 1.7 — Configure Workload Identity for ESO

```bash
gcloud iam service-accounts add-iam-policy-binding \
  eso-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[external-secrets/external-secrets]"

gcloud iam service-accounts add-iam-policy-binding \
  eso-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[default/eso-sa]"
```


### 1.8 — Create the Vertex AI + Pub/Sub service account and key

`review-service`, `review-worker`, and `recommendations-service` use a JSON key to authenticate with Pub/Sub and Vertex AI (Gemini 1.5 Flash). The key must exist as `sa-key.json` in the repository root before the Ansible deployment runs.

```bash
gcloud iam service-accounts create review-intelligence-sa \
  --display-name="Review Intelligence SA" \
  --project="${PROJECT_ID}"

SA_EMAIL="review-intelligence-sa@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.serviceAgent"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/pubsub.publisher"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/pubsub.subscriber"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/serviceusage.serviceUsageConsumer"

gcloud iam service-accounts keys create sa-key.json \
  --iam-account="${SA_EMAIL}"
```


### 1.9 — Create Pub/Sub topic and subscription

```bash
gcloud pubsub topics create review-created --project="${PROJECT_ID}"

gcloud pubsub subscriptions create review-worker-sub \
  --topic=review-created \
  --ack-deadline=60 \
  --project="${PROJECT_ID}"

gcloud pubsub subscriptions add-iam-policy-binding review-worker-sub \
  --member="serviceAccount:review-intelligence-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/pubsub.subscriber"

gcloud pubsub topics add-iam-policy-binding review-created \
  --member="serviceAccount:review-intelligence-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
```


## Part 2 — Deploy the project

Expected structure:

```text
~/CC2526-Group8/
├── Terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── terraform.tfvars
│   └── providers.tf
├── Ansible/
│   ├── ansible.cfg
│   ├── requirements.yml
│   ├── inventory/
│   │   └── dev.yml
│   ├── playbooks/
│   │   └── deploy.yml
│   └── roles/
│       ├── gke_auth/
│       │   └── tasks/main.yml
│       ├── cleanup/
│       │   └── tasks/main.yml
│       ├── namespace/
│       │   └── tasks/main.yml
│       ├── external_secrets/
│       │   └── tasks/main.yml
│       ├── ingress_nginx/
│       │   └── tasks/main.yml
│       ├── cert_manager/
│       │   └── tasks/main.yml
│       ├── secret_sync/
│       │   └── tasks/main.yml
│       ├── app_config/
│       │   └── tasks/main.yml
│       ├── postgres/
│       │   └── tasks/main.yml
│       ├── db_seed/
│       │   └── tasks/main.yml
│       ├── keycloak/
│       │   └── tasks/main.yml
│       ├── services/
│       │   └── tasks/main.yml
│       ├── security/
│       │   └── tasks/main.yml
│       ├── monitoring/
│       │   └── tasks/main.yml
│       ├── ingress/
│       │   └── tasks/main.yml
│       └── verify/
│           └── tasks/main.yml
├── k8s/
│   ├── 00-configmap.yaml
│   ├── 01-secret.yaml
│   ├── 01-secret-store.yaml
│   ├── 01-external-secret.yaml
│   ├── 02-postgres-users.yaml
│   ├── 02-postgres-movies.yaml
│   ├── 02-postgres-ratings.yaml
│   ├── 02-postgres-recommendations.yaml
│   ├── 02-postgres-subscriptions.yaml
│   ├── 02-postgres-badges.yaml
│   ├── 02-postgres-watchlists.yaml
│   ├── 03-populate-db-users.yaml
│   ├── 03-populate-db-movies.yaml
│   ├── 03-populate-db-ratings.yaml
│   ├── 03-populate-db-recommendations.yaml
│   ├── 03-populate-db-subscriptions.yaml
│   ├── 03-populate-db-badges.yaml
│   ├── 03-populate-db-watchlists.yaml
│   ├── 04-users-service.yaml
│   ├── 05-movies-service.yaml
│   ├── 06-reviews-service.yaml
│   ├── 07-review-worker.yaml
│   ├── 08-recommendations-service.yaml
│   ├── 09-badges-service.yaml
│   ├── 10-subscriptions-service.yaml
│   ├── 11-watchlists-service.yaml
│   ├── 12-keycloak.yaml
│   ├── 13-keycloak-setup-job.yaml
│   ├── 14-network-policies.yaml
│   ├── 15-cluster-issuer.yaml
│   ├── 16-monitoring-postgres.yaml
│   ├── 17-monitoring-bridge.yaml
│   ├── 18-monitoring-scrape.yaml
│   └── 19-ingress.yaml
└── sa-key.json
```


### Step 2 — Run Terraform

Go into the Terraform folder and apply the infrastructure.

```bash
cd ~/CC2526-Group8/Terraform
terraform init
terraform validate
terraform plan
terraform apply
```

After that, get the credentials again if needed:

```bash
gcloud container clusters get-credentials group8-cluster --zone europe-west1-b --project "$PROJECT_ID"
kubectl get nodes
```


### Step 3 — Prepare Ansible

Install Ansible if needed, then install the required collection and Python dependencies. The Kubernetes collection and the Python `kubernetes` library are required for the `kubernetes.core.k8s` module.

```bash
sudo apt update
sudo apt install -y ansible

cd ~/CC2526-Group8/Ansible
ansible-galaxy collection install -r requirements.yml
pip3 install --user kubernetes PyYAML jsonpatch
```

Verify the tools:

```bash
ansible --version
ansible-galaxy --version
python3 -c "import kubernetes; print('ok')"
```


### Step 4 — Configure Ansible inventory

Make sure `inventory/dev.yml` uses the correct Project ID and the correct absolute paths. The playbook depends on the Kubernetes manifests under `k8s/`.

Example:

```yaml
vars:
    gcp_project: cnprojeto
    gcp_zone: europe-west1-b
    gke_cluster_name: group8-cluster
    kube_namespace: default
    kubeconfig_path: "{{ lookup('env', 'KUBECONFIG') }}"
    manifests_dir: ~/CC2526-Group8/k8s
    sa_key_path: ~/CC2526-Group8/sa-key.json
    wait_timeout: 1800s
    ingress_namespace: ingress-nginx
    cert_manager_namespace: cert-manager
    external_secrets_namespace: external-secrets
    monitoring_namespace: monitoring
    eso_gcp_service_account: "eso-sa@{{ gcp_project }}.iam.gserviceaccount.com"
```


### Step 5 — Run the Ansible setup

This replaces the old `./deploy.sh` step. The playbook now handles ESO, the `eso-sa` ServiceAccount, NGINX Ingress, cert-manager, secret sync, database deployment, data population, Keycloak, microservices, network policies, monitoring, and ingress configuration.

```bash
cd ~/CC2526-Group8/Ansible
ansible-playbook playbooks/deploy.yml
```


## Part 3 — Accessing the project

### Service URLs

Get the NGINX IP first:

```bash
kubectl get svc ingress-nginx-controller -n ingress-nginx
```

Then use these URLs:

- Users: `https://<NGINX-IP>.nip.io/users-service/docs`
- Movies: `https://<NGINX-IP>.nip.io/movies-service/docs`
- Reviews: `https://<NGINX-IP>.nip.io/reviews-service/docs`
- Recommendations: `https://<NGINX-IP>.nip.io/recommendations-service/docs`
- Subscriptions: `https://<NGINX-IP>.nip.io/subscriptions-service/docs`
- Badges: `https://<NGINX-IP>.nip.io/badges-service/docs`
- Watchlists: `https://<NGINX-IP>.nip.io/watchlists-service/docs`

The TLS certificate is issued automatically by Let’s Encrypt and may take up to a minute after the first deploy.

### Authentication

Login happens directly against Keycloak. Port-forward it first:

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
| :-- | :-- |
| username | admin |
| email | [admin@cc2526.com](mailto:admin@cc2526.com) |
| password | AdminPassword123!@% |
| is_admin | true |

### LLM-powered endpoints

Explained recommendations, using Vertex AI synchronously:

```bash
curl -H "Authorization: Bearer <token>" \
  https://<NGINX-IP>.nip.io/recommendations-service/recommendations/<user_id>/explained
```

Submit a review, which triggers async Pub/Sub analysis:

```bash
curl -X POST https://<NGINX-IP>.nip.io/reviews-service/ratings \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "movie_id": 20, "rating": 4.5, "review": "Stunning visuals but flat acting."}'
```

This returns `201` immediately; the analysis happens in the background. The review summary endpoint reads from the database and does not call the LLM.

```bash
curl -H "Authorization: Bearer <token>" \
  https://<NGINX-IP>.nip.io/reviews-service/movies/<movie_id>/review-summary
```


## Part 4 — Checking cluster state

```bash
kubectl get pods -n default
kubectl get svc -n default
kubectl get externalsecret -n default
kubectl describe externalsecret group8-secret -n default
kubectl get certificate -n default
kubectl describe certificate group8-tls -n default
kubectl get ingress -n default
```

Logs per service:

```bash
kubectl logs deployment/users-service -n default
kubectl logs deployment/movies-service -n default
kubectl logs deployment/review-service -n default
kubectl logs deployment/review-worker -n default
kubectl logs deployment/recommendations-service -n default
kubectl logs deployment/badges-service -n default
kubectl logs deployment/subscriptions-service -n default
kubectl logs deployment/watchlists-service -n default
kubectl logs statefulset/keycloak -n default
```

Setup job logs:

```bash
kubectl logs job/keycloak-setup -n default
kubectl logs job/admin-db-init -n default
```

Tail `review-worker` to confirm it is listening for Pub/Sub messages:

```bash
kubectl logs -f deployment/review-worker -n default
```


## Ansible diagnostics

These commands are useful when the playbook needs troubleshooting. `--check` validates without changing resources, `--diff` shows what would change, and `--list-tasks` / `--list-tags` help inspect execution order.

```bash
cd ~/CC2526-Group8/Ansible
ansible-playbook playbooks/deploy.yml --check
ansible-playbook playbooks/deploy.yml --diff
ansible-playbook playbooks/deploy.yml --list-tasks
ansible-playbook playbooks/deploy.yml --list-tags
ansible-playbook playbooks/deploy.yml -vv
ansible-playbook playbooks/deploy.yml -vvv
```

You can also add `ansible.builtin.debug` tasks inside roles when you need to inspect variables such as paths, namespace names, or rendered manifests.

## Notes

Terraform is responsible only for the base infrastructure, so application YAML files are not needed during `terraform apply`. Ansible is responsible for the full Kubernetes deployment, so the `k8s/` manifests must exist and match the names expected by the playbook.

The most common source of errors in this setup is using the project number instead of the Project ID, or having the wrong namespace for `eso-sa` and the `SecretStore`. Keeping the `default` namespace consistent across the playbook, manifests, and Workload Identity bindings avoids those errors.