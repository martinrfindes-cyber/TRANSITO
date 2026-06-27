# Runbook de despliegue — Defensor Vial MX

Cómo dejar el bot corriendo **24/7**. El bot usa *long polling* (él consulta a
Telegram), por lo que **NO requiere abrir puertos, dominio, ni HTTPS**. Solo
necesita Python 3 y salida a internet.

---

## Opciones de hosting

| Opción | Ventaja | Cuándo usarla |
|---|---|---|
| **VPS Linux (tu Hostinger)** ✅ recomendada | Siempre encendido, barato, control total | Producción real |
| Tu laptop Windows | Cero costo extra | Pruebas; se apaga si cierras la compu |
| PaaS (Railway, Fly.io, Render) | Sin administrar servidor | Si no quieres tocar Linux |

La guía principal es para **tu VPS de Hostinger** (Linux). Al final hay una
sección para Windows.

---

## Requisitos previos

1. **Token de Telegram:** en Telegram, habla con **@BotFather** → `/newbot` →
   guarda el token.
2. **OPENAI_API_KEY:** de https://platform.openai.com/api-keys (con saldo).
3. Acceso SSH a tu VPS (usuario y contraseña/clave que te dio Hostinger).

---

## Despliegue en VPS Linux (Hostinger) — paso a paso

### 1. Conéctate por SSH
Desde tu PowerShell de Windows:
```bash
ssh root@TU_IP_DEL_VPS
```
(La IP está en el panel de Hostinger → VPS.)

### 2. Instala Python y git (si faltan)
En Ubuntu/Debian:
```bash
apt update && apt install -y python3 python3-venv python3-pip git
python3 --version   # confirma 3.10 o superior
```

### 3. Sube el proyecto al VPS
**Opción A — con git** (si lo subes a GitHub):
```bash
cd /opt
git clone TU_REPO defensor-vial
cd defensor-vial
```

**Opción B — copiando desde tu Windows** (sin git), desde tu PowerShell local:
```powershell
scp -r "C:\Users\CID MARTIN\OneDrive\Escritorio\TRANSITO" root@TU_IP:/opt/defensor-vial
```
> No copies `.env` con secretos por canales inseguros; mejor créalo en el VPS
> (paso 5). El `.gitignore` ya excluye `.env` y `/evidence/`.

### 4. Crea el entorno e instala dependencias
```bash
cd /opt/defensor-vial
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5. Configura las credenciales
```bash
cp .env.example .env
nano .env
```
Completa al menos:
```
TELEGRAM_BOT_TOKEN=123456:ABC...
OPENAI_API_KEY=sk-...
```
Guarda en nano con `Ctrl+O`, Enter, `Ctrl+X`.

### 6. Prueba que arranca
```bash
python main.py --check          # valida config y base de conocimiento
python main.py                  # arranca el bot; deberías ver "Bot en línea como @..."
```
Manda un mensaje al bot desde tu teléfono. Si responde, funciona. Detén con
`Ctrl+C` y sigue al paso 7 para dejarlo permanente.

### 7. Déjalo 24/7 con systemd (se reinicia solo)
Crea el servicio:
```bash
nano /etc/systemd/system/defensor-vial.service
```
Pega esto (ajusta la ruta si la cambiaste):
```ini
[Unit]
Description=Defensor Vial MX - bot de Telegram
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/defensor-vial
ExecStart=/opt/defensor-vial/.venv/bin/python /opt/defensor-vial/main.py
Restart=always
RestartSec=5
# Reinicia si el proceso cae (red caída, error inesperado, etc.)

[Install]
WantedBy=multi-user.target
```
Activa y arranca:
```bash
systemctl daemon-reload
systemctl enable defensor-vial      # arranca solo al reiniciar el VPS
systemctl start defensor-vial
systemctl status defensor-vial      # debe decir "active (running)"
```

¡Listo! El bot queda corriendo permanentemente y se reinicia solo si falla o si
reinicias el servidor.

---

## Operación diaria

```bash
systemctl status defensor-vial          # ¿está vivo?
journalctl -u defensor-vial -f          # ver logs en vivo (Ctrl+C para salir)
journalctl -u defensor-vial -n 100      # últimas 100 líneas
systemctl restart defensor-vial         # reiniciar
systemctl stop defensor-vial            # detener
```

### Actualizar a una versión nueva del código
```bash
cd /opt/defensor-vial
git pull                                # o vuelve a copiar con scp
source .venv/bin/activate
pip install -r requirements.txt         # por si hay deps nuevas
systemctl restart defensor-vial
```

---

## Alternativa: dejarlo en tu laptop Windows

Sirve para pruebas, pero **se apaga si cierras o suspendes la laptop**.

- **Rápido (mientras pruebas):** abre PowerShell en la carpeta del proyecto y
  corre `python main.py`. Déjalo abierto.
- **Permanente:** usa **NSSM** (https://nssm.cc) para registrarlo como servicio
  de Windows, o el **Programador de tareas** con "Ejecutar al iniciar sesión" y
  reinicio ante fallo. Apunta a `python.exe main.py` en la carpeta del proyecto.

Para 24/7 real conviene el VPS: la laptop no siempre está encendida.

---

## Seguridad y costos

- **Nunca** subas `.env` a GitHub ni lo compartas. El `.gitignore` ya lo protege.
- Si filtras un token, regéneralo: en @BotFather (`/revoke`) y en OpenAI (rota la
  key).
- **Costo de OpenAI:** se cobra por uso. Cada consulta de texto y cada
  `/analizar` (visión) consume tokens. Pon un **límite de gasto mensual** en el
  panel de OpenAI (Billing → Usage limits) para evitar sorpresas.
- **Evidencia de usuarios:** se guarda en `/opt/defensor-vial/evidence/`. Son
  datos personales; respáldalos y protégelos. No los subas a repos.

---

## Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| "Token de Telegram inválido" | `TELEGRAM_BOT_TOKEN` mal copiado | Revisa el `.env` |
| El bot no responde | Servicio caído | `systemctl status` y `journalctl -u defensor-vial` |
| "Falta OPENAI_API_KEY" | No está en `.env` | Agrégala y `systemctl restart` |
| Error 429 de OpenAI | Sin saldo o límite excedido | Revisa Billing en OpenAI |
| `/analizar` falla | Foto ilegible o sin saldo de visión | Foto más nítida / revisa saldo |
| Se cae tras reiniciar el VPS | Falta `systemctl enable` | Córrelo una vez |
