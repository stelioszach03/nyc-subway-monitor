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

# Χωρίς quotes στην τιμή
ENV TRAINING_SCHEDULE=0 */1 * * *

# Απλοποιημένο script απευθείας στο /etc/crontabs/root
RUN echo "${TRAINING_SCHEDULE} python /app/train.py && curl -s -X POST http://ml:8000/reload-model" > /etc/crontabs/root \
    && echo "" >> /etc/crontabs/root \
    && chmod 644 /etc/crontabs/root \
    && crontab -l

ENTRYPOINT ["/app/entrypoint.sh"]