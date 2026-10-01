# Cloud deployment preparation

Status: **prepared locally; not deployed or verified in a cloud**. Deployment is
deferred until the mandatory PDF work is reviewed. This pack is a single-node
demo, not a solution to the PDF's HA, 100K/sec or 99.9% requirements.

## Account and cost boundary

Use [Azure for Students](https://azure.microsoft.com/en-us/free/students), which
requires student verification but no credit card and supplies $100 credit usable
within 12 months. This is limited credit, not permanent free VM hosting.
Keep spending protection enabled and never upgrade to pay-as-you-go.
Terraform refuses subscriptions whose quota ID does not identify a student
offer or whose spending limit is not `On`.

Before provisioning, check the allowed region, VM quota, remaining credit and
the current regional estimate for the VM **plus 64 GiB disk, Standard public IP
and network traffic**. A daily shutdown schedule deallocates compute at 18:00 UTC
(23:30 IST) by default; disks and public IPs continue consuming credit. No paid
fallback, managed Kubernetes cluster or load balancer is created.
Oracle was rejected because the user cannot complete card verification.

## Infrastructure (do not apply until deployment phase)

Prerequisites: Terraform >=1.7, Azure CLI authenticated to the student account,
SSH key pair, and a reviewed regional estimate. Keep the private key outside the
repository. Register `Microsoft.Compute`, `Microsoft.Network`, and
`Microsoft.DevTestLab` in the subscription if not already registered.

```bash
az login
az account set --subscription YOUR_STUDENT_SUBSCRIPTION_ID
cp infra/terraform/azure/terraform.tfvars.example infra/terraform/azure/terraform.tfvars
# Edit the local tfvars: subscription, allowed location, public key, your /32 IP.
# Set credit_and_price_checked only after checking the estimate and free credit.
terraform -chdir=infra/terraform/azure init
terraform -chdir=infra/terraform/azure validate
terraform -chdir=infra/terraform/azure plan -out=reviewed.tfplan
# Review all resources and spending protection before the eventual deployment:
terraform -chdir=infra/terraform/azure apply reviewed.tfplan
terraform -chdir=infra/terraform/azure output -raw public_ip
```

Terraform creates one AMD64 Ubuntu 24.04 VM (2 CPUs, 8 GiB RAM), a 64 GiB boot
disk, virtual network, restricted SSH rule and shutdown schedule. Cloud-init
installs Docker and pinned K3s with secrets encryption. Only your SSH IP can
reach the host; Kubernetes, database and application ports are not public.
No account, Terraform plan against an account, VM, public URL or live cloud test
has been verified yet. Azure VM size/region availability must be checked at deployment.

## Transfer and start the application

Create a source bundle locally. This includes pending source changes without
committing or publishing them; it excludes local credentials, generated files,
dependency caches and Terraform state.

```bash
tar --exclude='node_modules' --exclude='dist' --exclude='__pycache__' \
  --exclude='.terraform' --exclude='*.tfvars' --exclude='*.tfstate*' \
  --exclude='*.tfplan' --exclude='test-results' --exclude='playwright-report' \
  -czf /tmp/valeosense-source.tgz backend processor simulator shared scripts \
  archive infra frontend requirements.lock requirements-iceberg.lock .dockerignore
scp /tmp/valeosense-source.tgz ubuntu@VM_IP:/tmp/
ssh ubuntu@VM_IP
sudo cloud-init status --wait
mkdir -p ~/valeosense
tar -xzf /tmp/valeosense-source.tgz -C ~/valeosense
cd ~/valeosense
bash scripts/cloud/deploy.sh
```

The script builds native images on the VM and imports them into the single K3s
node; no paid registry or public image upload is needed. It generates credentials
inside the cluster, waits for stores, completes the idempotent 100K-vehicle seed,
then starts the API, processor, simulator and dashboard. The simulator is set to
**10 events/sec over 50 active vehicles**, not the PDF's capacity target.

The base uses the existing `ANALYTICS_ROUTE=direct` configuration. It does not
deploy the optional QueryFlux/DuckDB, Iceberg or monitoring services yet. A
cloud dual-engine claim requires their manifests and separate native lineage
verification; the local root Compose demo remains unchanged.

## Collect real evidence

On the VM, after fresh telemetry is visible:

```bash
sudo k3s kubectl -n valeosense get pods,pvc
sudo k3s kubectl -n valeosense exec deployment/backend -- \
  python -m scripts.verify_cloud > /tmp/valeosense-cloud-verification.json
sudo k3s kubectl -n valeosense port-forward --address=127.0.0.1 service/frontend 3000:8080
```

In another local terminal:

```bash
ssh -N -L 3000:127.0.0.1:3000 ubuntu@VM_IP
```

Open `http://localhost:3000`. The services run on the cloud VM even when the
laptop disconnects; the SSH forwarding session only provides private browser
access. This is **not a public reviewer link**. Retrieve the API key privately
from the Kubernetes Secret when signing into the dashboard; never record it.
Capture advancing telemetry, vehicle history and the verification JSON, with
VM identity, date and source revision. Public HTTPS/OIDC ingress is separate work.

## Portability and lifecycle

The Kubernetes base uses standard Deployments, ClusterIP Services, a Job,
ConfigMaps, a Secret and PVCs. It needs a default dynamic StorageClass and does
not reference an Azure API. K3s supplies local-path storage. On another provider,
use an equivalent Linux node, install K3s and run the same source bundle; change
infrastructure configuration only. A second-provider run remains unverified.
For multi-node clusters, publish immutable images to a registry and select
appropriate replicated storage; the import script deliberately rejects them.

Local-path volumes survive pod restarts but not VM/disk loss. PVC size requests
are not disk quotas with local-path storage. Monitor host disk usage; the current
ClickHouse retention is 30 days and Kafka retention is bounded. Backups, automated
archive expiry, replicated stores and failover remain mandatory work.

Use Azure **Stop (deallocate)** between demos; an OS shutdown alone is not the
cost-control procedure. Remove resources after submission when no longer needed.
The VM has `prevent_destroy` to prevent accidental data loss; deliberate teardown
requires backing up needed evidence and explicitly removing that guard before
reviewing `terraform destroy`. Retained resources still consume student credit.

References checked 1 October 2026: [student offer](https://azure.microsoft.com/en-us/free/students),
[subscription spending-limit fields](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/subscription),
[K3s requirements](https://docs.k3s.io/installation/requirements).
