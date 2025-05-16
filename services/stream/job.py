# services/stream/job.py
import os
import json
from typing import Dict, Any, List
from datetime import datetime, timedelta

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    from_json, col, window, expr, to_timestamp, 
    avg, max as spark_max, min as spark_min, count,
    coalesce, lit  # Προσθήκη των coalesce και lit για τον χειρισμό NULL
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, 
    TimestampType, IntegerType, ArrayType, BooleanType
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

# Simplified schema for parsed GTFS-RT feed
train_schema = StructType([
    StructField("trip_id", StringType(), True),
    StructField("route_id", StringType(), True),
    StructField("timestamp", StringType(), True),
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
        .filter("key IS NOT NULL AND value IS NOT NULL")  # Προσθήκη φίλτρου για NULL values
    )

def send_to_redis_sync(batch_df, batch_id):
    """Synchronous function to send data to Redis."""
    # Create Redis client
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=int(REDIS_PORT),
        decode_responses=True,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
        retry_on_timeout=True
    )
    
    try:
        if not batch_df.isEmpty():
            # Convert batch to list of dictionaries
            rows = batch_df.toJSON().collect()
            
            # Create a Redis pipeline for efficiency
            with redis_client.pipeline() as pipe:
                for row in rows:
                    try:
                        data = json.loads(row)
                        
                        # Convert timestamp from ISO string to timestamp
                        timestamp_str = data.get("timestamp", "")
                        try:
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')).timestamp()
                        except (ValueError, TypeError):
                            # Fallback to current timestamp if parsing fails
                            timestamp = datetime.now().timestamp()
                        
                        # Store train position in Redis
                        if data.get("latitude") and data.get("longitude"):
                            train_key = f"train:{data['route_id']}:{data['trip_id']}"
                            pipe.hset(train_key, mapping={
                                "lat": str(data["latitude"]),
                                "lon": str(data["longitude"]),
                                "status": data.get("current_status", "UNKNOWN"),
                                "delay": int(data.get("delay", 0)),
                                "timestamp": int(timestamp),
                                "vehicle_id": data.get("vehicle_id", "unknown"),
                                "direction_id": int(data.get("direction_id", 0))
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
                    except Exception as e:
                        print(f"Error processing row: {e}")
                        continue
                
                # Execute all commands in the pipeline
                pipe.execute()
                print(f"Successfully processed batch {batch_id} with {len(rows)} records")
    except Exception as e:
        print(f"Error sending to Redis: {e}")
    finally:
        redis_client.close()

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
        # Convert timestamp string to timestamp type
        .withColumn("timestamp", to_timestamp(col("timestamp")))
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
            # Χρησιμοποιούμε coalesce για να αποφύγουμε τα NULL values
            coalesce(avg(col("delay")), lit(0.0)).alias("avg_delay"),
            coalesce(spark_max(col("delay")), lit(0)).alias("max_delay"), 
            coalesce(spark_min(col("delay")), lit(0)).alias("min_delay"),
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
        .foreachBatch(send_to_redis_sync)
        .outputMode("update")
        .start()
    )
    
    # Wait for termination - ΔΙΟΡΘΩΘΗΚΕ Η ΓΡΑΜΜΗ ΠΑΡΑΚΑΤΩ
    # Αυτή είναι η σημαντική αλλαγή - περιμένουμε και τα δύο streams
    print("Starting streams - awaiting termination")
    spark.streams.awaitAnyTermination()

if __name__ == "__main__":
    print("Starting NYC Subway Stream Processor...")
    
    # Initialize Spark
    try:
        spark = init_spark()
        print("Spark session initialized successfully")
        
        # Process streaming data
        process_stream(spark)
    except Exception as e:
        print(f"Error in stream processing: {e}")
        import traceback
        print(traceback.format_exc())