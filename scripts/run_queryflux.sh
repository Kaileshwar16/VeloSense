#!/usr/bin/env bash
set -euo pipefail
# Use an existing upstream build, never modify its source tree.
qf_repo="${QUERYFLUX_REPO:-/home/kailesh/work/queryflux}"
qf_binary="${QUERYFLUX_BINARY:-$qf_repo/target/debug/queryflux}"
if [[ ! -x "$qf_binary" ]]; then
  echo 'Set QUERYFLUX_BINARY to a built upstream QueryFlux binary.' >&2
  exit 1
fi
qf_python_lib="$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')"
export LD_LIBRARY_PATH="$qf_repo/target/debug/deps:$qf_python_lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$qf_repo/.venv/lib/python3.12/site-packages:${PYTHONPATH:-}"
export QUERYFLUX_ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
.venv/bin/python -m scripts.queryflux_config
exec "$qf_binary" --config artifacts/queryflux.local.yaml "$@"
