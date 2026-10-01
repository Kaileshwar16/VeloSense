#!/usr/bin/env bash
# Run on the target VM, from the unpacked repository. No Terraform apply here.
set -euo pipefail
cd "$(dirname "$0")/../.."
command -v k3s >/dev/null
command -v docker >/dev/null
sudo k3s kubectl wait --for=condition=Ready node --all --timeout=180s
if [ "$(sudo k3s kubectl get nodes -o name | wc -l)" -ne 1 ]; then
  echo 'This importer is for one-node demos. Use a registry for multi-node deployment.' >&2
  exit 1
fi
cloud_tag="$(date -u +%Y%m%d%H%M%S)"
cloud_work="$(mktemp -d)"
trap 'rm -rf -- "$cloud_work"' EXIT
cp -R infra/kubernetes/base "$cloud_work/base"
sudo docker build -f infra/Dockerfile -t "valeosense-app:$cloud_tag" .
sudo docker build -t "valeosense-frontend:$cloud_tag" frontend
sudo docker save "valeosense-app:$cloud_tag" "valeosense-frontend:$cloud_tag" |
  sudo k3s ctr images import -
cat >> "$cloud_work/base/kustomization.yaml" <<EOF
images:
  - name: valeosense-app
    newTag: '$cloud_tag'
  - name: valeosense-frontend
    newTag: '$cloud_tag'
EOF
kube() { sudo k3s kubectl -n valeosense "$@"; }
sudo k3s kubectl apply -f infra/kubernetes/base/namespace.yaml
# Generate once inside the cluster. Do not copy the laptop .env or rotate a
# PostgreSQL credential without changing the initialized database as well.
if ! kube get secret valeosense-secrets >/dev/null 2>&1; then
  python3 - <<'PY' | kube apply -f -
import json, secrets
password = secrets.token_urlsafe(32)
print(json.dumps({"apiVersion":"v1","kind":"Secret","metadata":{
    "name":"valeosense-secrets"},"type":"Opaque","stringData":{
    "API_KEY":secrets.token_urlsafe(32),"POSTGRES_PASSWORD":password,
    "DATABASE_URL":f"postgresql://valeosense:{password}@postgres:5432/valeosense"}}))
PY
fi
kube apply -k "$cloud_work/base" -l valeosense.io/phase=infra
for store in postgres redis redpanda clickhouse; do
  kube rollout status "deployment/$store" --timeout=600s
done
# Only the repeatable bootstrap job is replaced; PVCs are preserved.
kube delete job seed --ignore-not-found --wait=true
kube apply -k "$cloud_work/base" -l valeosense.io/phase=seed
kube wait --for=condition=Complete job/seed --timeout=900s
kube apply -k "$cloud_work/base" -l valeosense.io/phase=runtime
for app in backend processor simulator frontend; do
  kube rollout status "deployment/$app" --timeout=300s
done
kube get pods,pvc
echo 'Workloads started. Run the documented live verification before claiming success.'
