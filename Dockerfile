# Defensor Vial MX — bot de Telegram (long-polling, sin servidor web).
# Imagen ligera: única dependencia externa es python-dotenv; el resto es stdlib.
FROM python:3.12-slim

WORKDIR /app

# Instala dependencias primero (mejor caché de capas).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el código y la base de conocimiento.
COPY . .

# Logs en tiempo real (sin buffer) y consola en UTF-8.
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

# Arranca el bot. No expone puertos: usa long-polling contra Telegram.
CMD ["python", "main.py"]
