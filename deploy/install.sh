#!/usr/bin/env bash
# Despliegue de Defensor Vial MX en un VPS Ubuntu (probado en 24.04).
# Idempotente: puedes volver a correrlo cuando haya cambios (hace pull y reinicia).
set -euo pipefail

# La carpeta del proyecto es la carpeta padre de este script.
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="defensor-vial"

echo "==> Proyecto en: ${APP_DIR}"

# 1. Dependencias del sistema.
echo "==> Instalando python3, venv y git..."
apt-get update -y
apt-get install -y python3 python3-venv git

# 2. Entorno virtual + dependencias de Python (solo python-dotenv).
if [ ! -d "${APP_DIR}/.venv" ]; then
  echo "==> Creando entorno virtual..."
  python3 -m venv "${APP_DIR}/.venv"
fi
"${APP_DIR}/.venv/bin/pip" install --upgrade pip >/dev/null
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

# 3. Archivo .env (NO se versiona; lleva tus llaves reales).
if [ ! -f "${APP_DIR}/.env" ]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  echo ""
  echo "!! FALTA configurar tus llaves."
  echo "!! Edita ${APP_DIR}/.env  ->  TELEGRAM_BOT_TOKEN y OPENAI_API_KEY"
  echo "!! y luego corre:  systemctl restart ${SERVICE_NAME}"
fi

# 4. Servicio systemd (corre 24/7 y se reinicia solo).
echo "==> Instalando servicio systemd..."
sed "s#__APP_DIR__#${APP_DIR}#g" "${APP_DIR}/deploy/${SERVICE_NAME}.service" \
  > "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}" >/dev/null

echo ""
echo "==> Listo. Comandos utiles:"
echo "    systemctl start ${SERVICE_NAME}     # iniciar el bot"
echo "    systemctl restart ${SERVICE_NAME}   # reiniciar (tras editar .env o actualizar)"
echo "    systemctl status ${SERVICE_NAME}    # ver estado"
echo "    journalctl -u ${SERVICE_NAME} -f    # ver logs en vivo"
