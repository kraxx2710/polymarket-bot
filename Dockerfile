FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway setzt Env Vars über das Dashboard, nicht über .env
# Daher kein COPY .env

CMD ["python", "bot.py"]
