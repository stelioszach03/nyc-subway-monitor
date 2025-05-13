FROM apache/spark:3.5.5-python3

USER root

WORKDIR /app

# Add PostgreSQL JDBC driver
RUN wget https://jdbc.postgresql.org/download/postgresql-42.6.0.jar -O /opt/spark/jars/postgresql-42.6.0.jar

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better cache utilization
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYSPARK_PYTHON=python3
ENV PYSPARK_DRIVER_PYTHON=python3
ENV PYTHONUNBUFFERED=1

# Run with PostgreSQL driver
CMD ["spark-submit", "--packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.5,org.postgresql:postgresql:42.6.0", "--conf", "spark.executor.extraClassPath=/opt/spark/jars/postgresql-42.6.0.jar", "--conf", "spark.driver.extraClassPath=/opt/spark/jars/postgresql-42.6.0.jar", "job.py"]