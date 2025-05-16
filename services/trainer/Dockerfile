FROM python:3.11.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc libpq-dev build-essential curl cron \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir \
        onnx==1.14.0 \
        skl2onnx==1.14.1 \
        onnxruntime==1.16.0 \
        -r requirements.txt

RUN mkdir -p /app/models
COPY train.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Αφαιρούμε τη γραμμή με το ENV TRAINING_SCHEDULE που προκαλεί το πρόβλημα
# Θα χρησιμοποιήσουμε την τιμή από το docker-compose

# Δεν απαιτείται πλέον η δημιουργία του crontab αρχείου εδώ
# Θα δημιουργηθεί δυναμικά στο entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]