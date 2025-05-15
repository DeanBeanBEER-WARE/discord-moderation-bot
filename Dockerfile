FROM python:3.11-slim

# Arbeitsverzeichnis setzen
WORKDIR /app

# Abhängigkeiten kopieren und installieren
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Restlichen Code kopieren (inkl. config.json, core/, utils/ etc.)
COPY . .

# Startbefehl
CMD ["python", "main.py"] 