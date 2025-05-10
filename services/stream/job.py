# services/stream/job.py
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
import redis.asyncio as aioredis  # ΑΛΛΑΓΗ: async redis
import asyncio

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

async def send_to_redis_async(batch_df, batch_id):
    """Async function to send data to Redis."""
    # Create async Redis client
    redis_client = await aioredis.from_url(
        f"redis://{REDIS_HOST}:{REDIS_PORT}",
        encoding="utf-8",
        decode_responses=True
    )
    
    try:
        if not batch_df.isEmpty():
            # Convert batch to list of dictionaries
            rows = batch_df.toJSON().collect()
            
            # Create a Redis pipeline for efficiency
            async with redis_client.pipeline() as pipe:
                for row in rows:
                    data = json.loads(row)
                    
                    # Store train position in Redis
                    if data.get("latitude") and data.get("longitude"):
                        train_key = f"train:{data['route_id']}:{data['trip_id']}"
                        await pipe.hset(train_key, mapping={
                            "lat": data["latitude"],
                            "lon": data["longitude"],
                            "status": data["current_status"],
                            "delay": data.get("delay", 0),
                            "timestamp": int(datetime.now().timestamp()),
                            "vehicle_id": data.get("vehicle_id", "unknown"),
                            "direction_id": data.get("direction_id", 0)
                        })
                        # Set expiration to 5 minutes
                        await pipe.expire(train_key, 300)
                    
                    # Publish update to WebSocket channel
                    await pipe.publish(
                        "train-updates", 
                        json.dumps({
                            "type": "position",
                            "data": data
                        })
                    )
                
                # Execute all commands in the pipeline
                await pipe.execute()
    finally:
        await redis_client.close()

def process_stream(spark: SparkSession) -> None:
    """Process incoming GTFS-RT data stream."""
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
    
    # Write train positions to Redis - USING ASYNC
    def send_to_redis(batch_df, batch_id):
        """Send each row to Redis for real-time updates using async."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_to_redis_async(batch_df, batch_id))
        loop.close()
    
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