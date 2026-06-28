# Despliegue en VPS (Ubuntu)

Pasos para correr **Defensor Vial MX** 24/7 en un VPS Ubuntu, usando la
*terminal del navegador* del panel de Hostinger (o cualquier SSH).

> El bot usa **long-polling**: NO necesita dominio, SSL ni puertos abiertos.
> Única dependencia externa: `python-dotenv`.

## 1. Clonar el proyecto

```bash
cd /root
git clone https://github.com/martinrfindes-cyber/TRANSITO.git
```

> Si el repo es **privado**, este `clone` pedirá usuario/contraseña. Usa tu
> usuario de GitHub y un **token de acceso personal** (Settings → Developer
> settings → Personal access tokens) en lugar de la contraseña. Si el repo es
> público, clona sin pedir nada.

## 2. Instalar (instala Python, venv, dependencias y el servicio)

```bash
bash /root/TRANSITO/deploy/install.sh
```

## 3. Poner tus llaves

```bash
nano /root/TRANSITO/.env
```

Llena al menos:

- `TELEGRAM_BOT_TOKEN=...`
- `OPENAI_API_KEY=...`
- `LLM_PROVIDER=openai`

Guarda con `Ctrl+O`, `Enter`, y sal con `Ctrl+X`.

## 4. Arrancar

```bash
systemctl start defensor-vial
systemctl status defensor-vial      # debe decir "active (running)"
journalctl -u defensor-vial -f      # logs en vivo (Ctrl+C para salir)
```

Cuando veas `Bot conectado como @...`, ya está vivo 24/7.

## Actualizar a una versión nueva

```bash
cd /root/TRANSITO && git pull
bash deploy/install.sh
systemctl restart defensor-vial
```

## Importante

- **No corras el bot en dos lugares a la vez** (local + VPS). Telegram solo
  permite un consumidor de mensajes por token (error de *getUpdates conflict*).
  Antes de arrancar en el VPS, apaga el bot local.
- La evidencia se guarda en `/root/TRANSITO/evidence/` (configurable con
  `EVIDENCE_DIR`). El `.env` y `evidence/` no se versionan.
