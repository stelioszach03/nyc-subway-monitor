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

# Use double quotes for ENV value with spaces to make Docker build work
ENV TRAINING_SCHEDULE="0 */1 * * *"

RUN echo '#!/bin/sh\ncd /app && python train.py && curl -s -X POST http://ml:8000/reload-model' \
        > /app/train_cron.sh && chmod +x /app/train_cron.sh

ENTRYPOINT ["/app/entrypoint.sh"]