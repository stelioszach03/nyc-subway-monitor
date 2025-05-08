FROM python:3.11.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .
RUN mkdir -p /app/models

EXPOSE 8000

CMD ["uvicorn", "score:app", "--host", "0.0.0.0", "--port", "8000"]
