#!/usr/bin/env bash
# Container entrypoint.
# Pulls every SecureString parameter under $SSM_PATH from AWS SSM Parameter Store,
# exports each as an env var (key = parameter basename), then execs the CMD.
# Secrets are only ever in process memory — never written to disk.
#
# IAM: the EC2 instance role must allow ssm:GetParametersByPath + kms:Decrypt
# for the KMS key that encrypts the parameters.

set -euo pipefail

SSM_PATH="${SSM_PATH:-/aligniq/staging/}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Local dev short-circuit: skip SSM and trust whatever env is already set.
if [[ "${SKIP_SSM:-false}" == "true" ]]; then
  echo "[entrypoint] SKIP_SSM=true, using existing env"
  exec "$@"
fi

echo "[entrypoint] Fetching secrets from SSM path '${SSM_PATH}' in ${AWS_REGION}"

# Pull every parameter under the path. Pagination handled by --no-paginate=false (default).
# Output is shell-friendly: lines like  KEY='value with spaces and $special chars'
mapfile -t PARAMS < <(
  aws ssm get-parameters-by-path \
    --region "${AWS_REGION}" \
    --path "${SSM_PATH}" \
    --recursive \
    --with-decryption \
    --query "Parameters[].[Name,Value]" \
    --output text
)

if [[ ${#PARAMS[@]} -eq 0 ]]; then
  echo "[entrypoint] ERROR: no parameters found at ${SSM_PATH}" >&2
  exit 1
fi

count=0
for line in "${PARAMS[@]}"; do
  # Each line is "Name<TAB>Value". Value may itself contain tabs — split only on first tab.
  name="${line%%$'\t'*}"
  value="${line#*$'\t'}"
  key="${name##*/}"          # basename, e.g. /aligniq/staging/POSTGRES_PASSWORD -> POSTGRES_PASSWORD

  # Validate key looks like a real env var name (defensive).
  if [[ ! "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "[entrypoint] WARN: skipping non-env-safe key '${key}'" >&2
    continue
  fi

  export "${key}=${value}"
  count=$((count + 1))
done

echo "[entrypoint] Loaded ${count} env vars from SSM"
echo "[entrypoint] Launching: $*"

exec "$@"
