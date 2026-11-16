#!/usr/bin/env bash
# Implanta a imagem do OrderService num host Docker via SSH.
#
# Variáveis: IMAGE, ENVIRONMENT, APP_PORT, REGISTRY_USER, REGISTRY_TOKEN
# e, para deploy remoto, DEPLOY_HOST, DEPLOY_USER e DEPLOY_SSH_KEY (secrets do environment).
#
# Sem DEPLOY_HOST configurado, o script sobe o contêiner no próprio runner e faz o
# smoke test lá. Assim o pipeline funciona de ponta a ponta antes de existir um servidor.
set -euo pipefail

: "${IMAGE:?}" "${ENVIRONMENT:?}" "${APP_PORT:?}"
CONTAINER="orderservice-${ENVIRONMENT}"

run_container() {
  cat <<EOF
set -euo pipefail
echo "${REGISTRY_TOKEN}" | docker login ghcr.io -u "${REGISTRY_USER}" --password-stdin
docker pull "${IMAGE}"
docker rm -f "${CONTAINER}" 2>/dev/null || true
docker run -d --name "${CONTAINER}" --restart unless-stopped \
  --label "environment=${ENVIRONMENT}" \
  -p "${APP_PORT}:8000" "${IMAGE}"
EOF
}

smoke_test() {
  local url="$1"
  for _ in $(seq 1 20); do
    if curl -fsS "${url}/health" >/dev/null; then
      echo "Smoke test OK em ${url}"
      return 0
    fi
    sleep 3
  done
  echo "Smoke test falhou em ${url}" >&2
  return 1
}

if [[ -n "${DEPLOY_HOST:-}" ]]; then
  echo "Implantando ${IMAGE} em ${ENVIRONMENT} (${DEPLOY_HOST})"
  key_file="$(mktemp)"
  trap 'rm -f "${key_file}"' EXIT
  printf '%s\n' "${DEPLOY_SSH_KEY}" > "${key_file}"
  chmod 600 "${key_file}"
  run_container | ssh -i "${key_file}" -o StrictHostKeyChecking=accept-new \
    "${DEPLOY_USER}@${DEPLOY_HOST}" bash -s
  smoke_test "http://${DEPLOY_HOST}:${APP_PORT}"
else
  echo "DEPLOY_HOST não configurado: simulando o deploy de ${ENVIRONMENT} no runner"
  run_container | bash -s
  smoke_test "http://localhost:${APP_PORT}"
fi
