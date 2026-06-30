# Phase 6 – Non-Functional Requirements and Technical Architecture

**CC2526 – Group 8**

---

## 1. Introduction

This document outlines the plan for the final implementation and deployment phase of the project, focusing on **Automation via Infrastructure as Code (IaC)**. The current platform, consisting of several microservices (users, movies, reviews, recommendations, subscriptions, badges, and watchlists) deployed on GKE via Kubernetes, relies on manual `kubectl` and `gcloud` interventions. 

To improve reliability, scalability, and maintainability, the proposed improvement for this phase is the integration of **HashiCorp Terraform** to automate the infrastructure provisioning.

---

## 2. Problem Statement

### 2.1 Manual Infrastructure Management
The current infrastructure setup requires manual execution of multiple commands in the Cloud Shell, making the environment:
- **Prone to error**: Manual commands can be mistyped, and steps forgotten, leading to environment inconsistencies.
- **Difficult to reproduce**: Re-creating the cluster, namespace, or core configurations requires a clean slate and perfect recall of the deployment order.
- **Not version-controlled**: Changes to the infrastructure are not tracked in Git, making audits and rollback of infrastructure changes impossible.

### 2.2 Lack of Lifecycle Management
Managing the lifecycle of the GKE cluster (creation, configuration, deletion) through ad-hoc CLI commands lacks a declarative approach. Changes are imperative, meaning there is no single source of truth for the desired state of the infrastructure.

---

## 3. Proposed Improvements

### 3.1 Terraform for Infrastructure Automation

We propose implementing **Terraform** to manage the lifecycle of our cloud infrastructure and core Kubernetes resources. Terraform provides a declarative way to define infrastructure as code, ensuring that the environment is versioned, repeatable, and easily manageable.

**What Terraform will automate:**

| Component | Responsibility |
|---|---|
| **GKE Cluster** | Provisioning the cluster, node pools, and basic network configuration. |
| **Namespaces** | Creation and management of the `group8` namespace. |
| **Core Configurations** | Automated application of `ConfigMaps` and `Secrets` (or integration with secret stores). |

**Terraform architecture in this project:**
- The Terraform configuration will exist outside the Kubernetes cluster (e.g., in Google Cloud Shell).
- It uses the **Google Provider** to interface with GCP APIs (GKE, VPC, etc.).
- It uses the **Kubernetes Provider** to manage internal resources (`namespace`, `configmaps`, etc.).

---

## 4. Non-Functional Requirements

| ID | Requirement | Addressed by |
|---|---|---|
| NFR-01 | **Reproducibility**: The entire infrastructure must be re-creatable from code | Terraform |
| NFR-02 | **Version Control**: All infrastructure changes must be tracked in the Git repository | IaC (Terraform) |
| NFR-03 | **Automation**: Minimise manual CLI operations for cluster and resource management | Terraform Plan/Apply |
| NFR-04 | **Consistency**: Ensure dev, staging, and prod environments are identical | Declarative state management |
| NFR-05 | **Maintainability**: Simplify the lifecycle management of resources | IaC (Terraform) |

---

## 5. Deployment Plan

The implementation in Phase 7 will follow these steps:

### Step 1 — Terraform Setup
Organize the repository with a dedicated `terraform/` directory:
- `providers.tf`: Define GCP and Kubernetes providers.
- `variables.tf`: Define input variables (project ID, region, machine type).
- `main.tf`: Define GKE cluster and node pool.
- `k8s.tf`: Define Kubernetes namespace, configmaps, and secrets.

### Step 2 — Initialisation and Planning
```bash
cd terraform/
terraform init
terraform plan
```

### Step 3 — Apply Infrastructure
```bash
terraform apply -auto-approve
```

### Step 4 — Workload Deployment
Continue applying the Kubernetes manifests for microservices (already prepared) to the namespace created by Terraform:
```bash
kubectl apply -n group8 -f k8s/
```

---

## 6. Expected Outcomes
By automating our infrastructure with Terraform, we expect:
1. **Faster Onboarding**: New members can spin up the full infrastructure in minutes.
2. **Standardisation**: Every cluster created will adhere exactly to the defined configuration.
3. **Safety**: Changes are previewed (`terraform plan`) before application, reducing the risk of accidental resource destruction.
4. **Readiness for CI/CD**: The infrastructure layer is now ready to be integrated into an automated pipeline in Phase 8.
