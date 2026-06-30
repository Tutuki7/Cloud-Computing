# Guide to Deploy Terraform and Ansible on GCP

This guide explains the steps required to get **Terraform** and **Ansible** working on Google Cloud Platform for the Group8 project, including the adjustments needed during Cloud Shell testing.

## Objective

The correct separation in this project is: **Terraform** to create base infrastructure on GCP (GKE cluster, node pool, namespace), and **Ansible** to deploy the Kubernetes application using YAML files.

Application `.yaml` files are **not required during `terraform apply`** when Terraform is only creating infrastructure. These manifests are only needed when executing the application deployment, in this case with Ansible.

## File Structure

File organization must be consistent for Terraform, Ansible, and Kubernetes manifests to work together.

### Terraform

The Terraform folder should be structured like this:

```text
~/terraform/
├── main.tf
├── variables.tf
├── outputs.tf
├── terraform.tfvars
└── providers.tf
```

File descriptions:

- `main.tf`: defines main resources like GKE cluster, node pool, and Kubernetes namespace
- `variables.tf`: declares project variables like `project_id`, `region`, `zone`, and resource names
- `outputs.tf`: exposes useful information after `apply` (cluster name, region, etc.)
- `terraform.tfvars`: contains concrete variable values for the target environment
- `providers.tf`: defines providers like `google` and optionally `kubernetes`

### Ansible

The Ansible folder is organized as follows:

```text
~/Ansible/
├── ansible.cfg
├── requirements.yml
├── README.md
├── inventory/
│   └── dev.yml
├── playbooks/
│   └── deploy.yml
└── roles/
    ├── gke_auth/
    │   └── tasks/
    │       └── main.yml
    ├── namespace/
    │   └── tasks/
    │       └── main.yml
    ├── core/
    │   └── tasks/
    │       └── main.yml
    ├── services/
    │   └── tasks/
    │       └── main.yml
    ├── ingress/
    │   └── tasks/
    │       └── main.yml
    └── verify/
        └── tasks/
            └── main.yml
```

File descriptions:

- `ansible.cfg`: defines base Ansible options including default inventory and `roles_path`
- `requirements.yml`: installs `kubernetes.core` collection
- `inventory/dev.yml`: defines variables like `gcp_project`, `gcp_zone`, `gke_cluster_name`, `kube_namespace`, `manifests_dir`
- `playbooks/deploy.yml`: main playbook that calls roles in correct order
- `roles/gke_auth/tasks/main.yml`: gets cluster credentials with `gcloud container clusters get-credentials`
- `roles/namespace/tasks/main.yml`: ensures `group8` namespace exists
- `roles/core/tasks/main.yml`: applies `ConfigMap`, `Secret`, `Postgres`, and `populate-db`
- `roles/services/tasks/main.yml`: applies microservices and waits for rollouts
- `roles/ingress/tasks/main.yml`: applies Ingress
- `roles/verify/tasks/main.yml`: performs final verification with `kubectl`

### Kubernetes

The `k8s/` folder should contain manifests applied by Ansible:

```text
~/k8s/
├── 00-configmap.yaml
├── 01-secret.yaml
├── 02-postgres.yaml
├── 03-populate-db.yaml
├── 04-users-service.yaml
├── 05-movies-service.yaml
├── 06-reviews-service.yaml
├── 07-subscriptions-service.yaml
├── 08-badges-service.yaml
├── 09-watchlists-service.yaml
└── 10-ingress.yaml
```

## Prerequisites

Before starting, ensure you have:

- Active Google Cloud Platform account and project
- Valid **Project ID** (not **project number**). `gcloud container clusters get-credentials` requires Project ID and fails with project number
- Google Cloud Shell or machine with `gcloud`, `kubectl`, `terraform`, `python3`, and `pip3` installed
- Ansible installed (`ansible-playbook` and `ansible-galaxy` commands must exist)
- `kubernetes.core` collection and Python `kubernetes` library (required for `kubernetes.core.k8s` modules)

## Expected Structure

Minimum structure used in testing:

```text
~/terraform/
~/Ansible/
~/k8s/
```

The `k8s/` folder must contain correct Kubernetes manifests with names matching the Ansible playbook expectations:

```text
00-configmap.yaml
01-secret.yaml
02-postgres.yaml
03-populate-db.yaml
04-users-service.yaml
05-movies-service.yaml
06-reviews-service.yaml
07-subscriptions-service.yaml
08-badges-service.yaml
09-watchlists-service.yaml
10-ingress.yaml
```

`ConfigMap`, `Secret`, and `Postgres` must be correctly defined as they are base resources used before microservice deployment.

## Terraform Steps

### 1. Enter Terraform folder

```bash
cd ~/terraform
```

### 2. Initialize Terraform project

```bash
terraform init
```

### 3. Validate configuration

```bash
terraform validate
```

### 4. Review execution plan

```bash
terraform plan
```

### 5. Apply infrastructure

```bash
terraform apply
```

If Terraform is correct, a GKE cluster and node pool should exist at completion.

### 6. Confirm in GCP

```bash
gcloud container clusters list
```

Cluster should appear in the list. Can also verify in Google Cloud Console → Kubernetes Engine.

## Get Correct Project ID

Most common error was using **project number** instead of **Project ID**. Get Project ID with:

```bash
gcloud config get-value project
```

or:

```bash
gcloud projects list
```

If value is like `476471572143`, that's the project number and won't work with `get-credentials`. Correct value is typically like `cloud-computing-project-fcul`.

## Ansible Steps

### 1. Install Ansible

If `ansible-galaxy` command doesn't exist, Ansible isn't installed:

```bash
sudo apt update
sudo apt install -y ansible
```

Verify:

```bash
ansible --version
ansible-galaxy --version
```

### 2. Install required collection

Enter Ansible folder and install collection:

```bash
cd ~/Ansible
ansible-galaxy collection install -r requirements.yml
```

`requirements.yml` installs `kubernetes.core` collection required for Kubernetes manifests with `k8s` module.

### 3. Install Python `kubernetes` library

Even with collection installed, playbook may fail if Python `kubernetes` library is missing from Ansible environment:

```bash
pip3 install --user kubernetes PyYAML jsonpatch
```

Test:

```bash
python3 -c "import kubernetes; print('ok')"
```

### 4. Configure `inventory/dev.yml`

`inventory/dev.yml` must use **Project ID** (not project number) and correct manifests path.

Working example:

```yaml
all:
  vars:
    ansible_python_interpreter: /usr/bin/python3
    gcp_project: cloud-computing-project-fcul
    gcp_zone: europe-west1-b
    gke_cluster_name: group8-cluster
    kube_namespace: group8
    kubeconfig_path: ~/.kube/config
    manifests_dir: /home/tiagotiago_f_pereira/k8s
    wait_timeout: 300s
```

Absolute path in `manifests_dir` was required because Ansible was resolving relative path `../k8s` incorrectly from roles context.

### 5. Get cluster credentials

Before running playbook, configure `kubectl` for GKE cluster:

```bash
gcloud container clusters get-credentials group8-cluster --zone europe-west1-b --project cloud-computing-project-fcul
```

Verify access:

```bash
kubectl get nodes
```

If nodes show `Ready`, cluster connection is correct.

### 6. Execute playbook

With everything configured:

```bash
cd ~/Ansible
ansible-playbook playbooks/deploy.yml
```

Playbook is designed to:

- Get cluster credentials
- Ensure namespace exists
- Apply `ConfigMap`, `Secret`, and `Postgres`
- Wait for Postgres to be ready
- Apply `populate-db` job
- Wait for job completion
- Apply microservices
- Wait for rollouts
- Apply Ingress and verify final state

## Errors Found and Solutions

### 1. `ansible-galaxy: command not found`

**Cause:** Ansible not installed

**Solution:**

```bash
sudo apt update
sudo apt install -y ansible
```

### 2. `The value of --project flag was set to Project number`

**Cause:** Used project number instead of Project ID in `inventory/dev.yml`

**Solution:** Replace with value like `cloud-computing-project-fcul`

### 3. `Failed to import the required Python library (kubernetes)`

**Cause:** Missing Python `kubernetes` library

**Solution:**

```bash
pip3 install --user kubernetes PyYAML jsonpatch
```

### 4. `Could not find or access '../k8s/00-configmap.yaml'`

**Cause:** Relative manifests path wrong in roles context

**Solution:** Use absolute path in `manifests_dir`:

```yaml
manifests_dir: /home/tiagotiago_f_pereira/k8s
```

### 5. Postgres wait timeout

**Cause:** Playbook failed waiting for Postgres pod `Ready` condition before `populate-db` even ran. Issue must be investigated in `group8` namespace (`kubectl get pods` without `-n group8` shows only `default` namespace)

**Useful diagnostic commands:**

```bash
kubectl get pods -n group8
kubectl get pvc -n group8
kubectl describe pod -n group8 -l app=postgres
kubectl describe pvc postgres-pvc -n group8
kubectl logs -n group8 -l app=postgres
```

If PVC shows `Pending`, Postgres may not start correctly due to persistent volume issues.

## Final Verifications

After running Ansible, these commands verify deployment status:

```bash
kubectl get pods -n group8
kubectl get jobs -n group8
kubectl get svc -n group8
kubectl get ingress -n group8
```

For specific rollout verification:

```bash
kubectl rollout status deployment/users-service -n group8
kubectl rollout status deployment/movies-service -n group8
kubectl rollout status deployment/review-service -n group8
kubectl rollout status deployment/subscriptions-service -n group8
kubectl rollout status deployment/badges-service -n group8
kubectl rollout status deployment/watchlists-service -n group8
```

Minimum success criteria:

- `terraform apply` completes without error and cluster exists
- `kubectl get nodes` shows `Ready` nodes
- `ansible-playbook` runs without failures
- Pods show `Running` or `Completed` in `group8` namespace
- `populate-db-phase5` job completes successfully
- Ingress receives IP and responds to expected endpoints

## Final Notes on YAMLs

Terraform doesn't depend on application manifests when only creating GKE/namespace, so `.yaml` files don't need to exist during `terraform apply`.

Ansible depends directly on manifests, so files must exist at `manifests_dir` path with names matching playbook expectations. Final `Ingress` must use service-specific paths (`/users`, `/movies`, `/reviews`, `/subscriptions`, `/badges`, `/watchlists`) instead of repeating `/`.