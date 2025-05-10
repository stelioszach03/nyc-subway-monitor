# nyc-subway-monitor/services/stream/job.py
import os
import json
from typing import Dict, Any, List
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    from_json, col, window, expr, to_timestamp, 
    avg, max as spark_max, min as spark_min, count
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, 
    TimestampType, IntegerType, ArrayType
)
import redis

# Configuration from environment variables
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "timescaledb")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "subway")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "subway_password")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "subway_monitor")
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")

# Schema for parsed GTFS-RT feed
train_schema = StructType([
    StructField("trip_id", StringType(), True),
    StructField("route_id", StringType(), True),
    StructField("timestamp", TimestampType(), True),
    StructField("stop_id", StringType(), True),
    StructField("stop_sequence", IntegerType(), True),
    StructField("latitude", DoubleType(), True),
    StructField("longitude", DoubleType(), True),
    StructField("current_status", StringType(), True),
    StructField("current_stop_sequence", IntegerType(), True),
    StructField("delay", IntegerType(), True),
    StructField("vehicle_id", StringType(), True),
    StructField("direction_id", IntegerType(), True)
])

# Schema for train delays aggregation
delay_schema = StructType([
    StructField("route_id", StringType(), True),
    StructField("avg_delay", DoubleType(), True),
    StructField("max_delay", IntegerType(), True),
    StructField("min_delay", IntegerType(), True),
    StructField("train_count", IntegerType(), True),
    StructField("window_start", TimestampType(), True),
    StructField("window_end", TimestampType(), True)
])

def init_spark() -> SparkSession:
    """Initialize Spark session with required configurations."""
    return (
        SparkSession.builder
        .appName("NYC-Subway-Stream")
        .config("spark.sql.streaming.checkpointLocation", "/tmp/checkpoint")
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.5")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.streaming.metricsEnabled", "true")
        .getOrCreate()
    )

def create_kafka_stream(spark: SparkSession) -> Any:
    """Create a DataFrame from the Kafka stream."""
    return (
        spark
        .readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("subscribe", "subway-feeds")
        .option("startingOffsets", "latest")
        .option("kafka.request.timeout.ms", "60000")
        .option("kafka.session.timeout.ms", "30000")
        .option("failOnDataLoss", "false")
        .load()
    )

def process_stream(spark: SparkSession) -> None:
    """Process incoming GTFS-RT data stream."""
    # Initialize Redis client for publishing real-time updates
    redis_client = redis.Redis(host=REDIS_HOST, port=int(REDIS_PORT))
    
    # Create Kafka stream
    kafka_stream = create_kafka_stream(spark)
    
    # Parse Kafka messages
    parsed_stream = (
        kafka_stream
        .selectExpr("CAST(value AS STRING) as json_data")
        .select(from_json(col("json_data"), train_schema).alias("data"))
        .select("data.*")
    )
    
    # Compute 1-minute windowed delay metrics by route
    windowed_delays = (
        parsed_stream
        .withWatermark("timestamp", "1 minute")
        .groupBy(
            window(col("timestamp"), "1 minute"),
            col("route_id")
        )
        .agg(
            avg(col("delay")).alias("avg_delay"),
            spark_max(col("delay")).alias("max_delay"),
            spark_min(col("delay")).alias("min_delay"),
            count("*").alias("train_count")
        )
        .select(
            col("route_id"),
            col("avg_delay"),
            col("max_delay"), 
            col("min_delay"),
            col("train_count"),
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end")
        )
    )
    
    # Write windowed metrics to TimescaleDB
    postgres_url = f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    postgres_properties = {
        "user": POSTGRES_USER,
        "password": POSTGRES_PASSWORD,
        "driver": "org.postgresql.Driver"
    }
    
    # Stream train positions to Redis
    def send_to_redis(batch_df, batch_id):
        """Send each row to Redis for real-time updates."""
        if not batch_df.isEmpty():
            # Convert batch to list of dictionaries
            rows = batch_df.toJSON().collect()
            
            # Create a Redis pipeline for efficiency
            with redis_client.pipeline() as pipe:
                for row in rows:
                    data = json.loads(row)
                    
                    # Store train position in Redis
                    if data.get("latitude") and data.get("longitude"):
                        train_key = f"train:{data['route_id']}:{data['trip_id']}"
                        pipe.hset(train_key, mapping={
                            "lat": data["latitude"],
                            "lon": data["longitude"],
                            "status": data["current_status"],
                            "delay": data.get("delay", 0),
                            "timestamp": int(datetime.now().timestamp())
                        })
                        # Set expiration to 5 minutes
                        pipe.expire(train_key, 300)
                    
                    # Publish update to WebSocket channel
                    pipe.publish(
                        "train-updates", 
                        json.dumps({
                            "type": "position",
                            "data": data
                        })
                    )
                
                # Execute all commands in the pipeline
                pipe.execute()
    
    # Write windowed delay metrics to TimescaleDB
    delay_stream = (
        windowed_delays.writeStream
        .foreachBatch(
            lambda batch_df, batch_id: batch_df.write
            .jdbc(
                url=postgres_url,
                table="train_delays",
                mode="append",
                properties=postgres_properties
            )
        )
        .outputMode("update")
        .start()
    )
    
    # Write train positions to Redis
    position_stream = (
        parsed_stream.writeStream
        .foreachBatch(send_to_redis)
        .outputMode("update")
        .start()
    )
    
    # Wait for termination
    spark.streams.awaitAnyTermination()

if __name__ == "__main__":
    spark = init_spark()
    process_stream(spark)
