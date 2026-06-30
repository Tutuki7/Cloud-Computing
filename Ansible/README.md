# Ansible deployment for Group8

## Prerequisites
- Ansible installed
- `gcloud` installed and authenticated
- `kubectl` installed
- Access to the target GKE cluster
- Kubernetes manifests available in `../k8s`

## Install collection
```bash
ansible-galaxy collection install -r requirements.yml
```

## Configure inventory
Edit `inventory/dev.yml` and set:
- `gcp_project`
- `gcp_zone`
- `gke_cluster_name`
- `kube_namespace`
- `manifests_dir`

## Run deployment
```bash
cd ansible
ansible-playbook playbooks/deploy.yml
```
