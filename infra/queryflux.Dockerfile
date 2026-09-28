# Keep the exact previously verified upstream binary and embedded DuckDB library.
FROM ghcr.io/lakeops-org/queryflux@sha256:1da899cddf3c95c41ac074d8dd6f3de59dd10050abc344fdd19528e874b4f2e3
USER root
RUN mkdir -p /data && chown 1000:1000 /data
COPY scripts/duckdb_snapshot.py scripts/queryflux_config.py /opt/valeosense/
COPY infra/queryflux.yaml /opt/valeosense/queryflux.yaml
USER queryflux
