FROM python:3.11.12-slim

WORKDIR /app

# Εγκατάσταση απαραίτητων πακέτων συστήματος
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    build-essential \
    curl \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Εγκατάσταση Python πακέτων
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install skl2onnx requests

# Δημιουργία φακέλου για μοντέλα
RUN mkdir -p /app/models

# Αντιγραφή αρχείων εκπαίδευσης
COPY train.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Ορισμός μεταβλητών περιβάλλοντος
ENV MODEL_OUTPUT_PATH=/app/models/anomaly_model.onnx
ENV TRAINING_SCHEDULE="0 */1 * * *"  # Κάθε 1 ώρα

# Δημιουργία αρχείου cron task
RUN echo "#!/bin/bash\ncd /app && python train.py && curl -X POST http://ml:8000/reload-model" > /app/train_cron.sh \
    && chmod +x /app/train_cron.sh

# Ορισμός entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]