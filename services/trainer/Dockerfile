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

# Δημιουργία του crontabs directory και του root file
RUN mkdir -p /etc/crontabs && touch /etc/crontabs/root && chmod 600 /etc/crontabs/root

ENTRYPOINT ["/app/entrypoint.sh"]