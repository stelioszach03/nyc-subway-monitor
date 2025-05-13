FROM python:3.11.12-slim

# Εγκατάσταση βασικών εξαρτήσεων
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Αντιγραφή αρχείου απαιτήσεων για καλύτερη χρήση της cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Αντιγραφή κώδικα εφαρμογής
COPY . .

EXPOSE 8000

# Ορισμός μεταβλητών περιβάλλοντος για βελτιωμένη απόδοση
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV WORKERS=4

# Εκκίνηση με uvicorn και βελτιστοποιημένες ρυθμίσεις
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port 8000 --workers ${WORKERS} --timeout-graceful-shutdown 30"]