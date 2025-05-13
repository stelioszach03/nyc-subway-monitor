-- Initialize Database and tables for NYC Subway Monitor

-- Create tables for train delays
CREATE TABLE IF NOT EXISTS train_delays (
    id SERIAL PRIMARY KEY,
    route_id VARCHAR(10) NOT NULL,
    avg_delay FLOAT NOT NULL,
    max_delay INTEGER NOT NULL,
    min_delay INTEGER NOT NULL,
    train_count INTEGER NOT NULL,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL
);

-- Try to create hypertable if TimescaleDB extension is available
DO $$
BEGIN
    -- Check if TimescaleDB extension exists
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        -- Create hypertable for time-series data
        PERFORM create_hypertable('train_delays', 'window_end', if_not_exists => TRUE);
    ELSE
        -- If TimescaleDB is not available, create regular indices
        RAISE NOTICE 'TimescaleDB extension not available, creating regular indices instead';
    END IF;
END
$$;

-- Create index for quick lookups by route_id and window_end
CREATE INDEX IF NOT EXISTS idx_train_delays_route_id ON train_delays (route_id);
CREATE INDEX IF NOT EXISTS idx_train_delays_window_end ON train_delays (window_end);

-- Create alerts table
CREATE TABLE IF NOT EXISTS alerts (
    id VARCHAR(50) PRIMARY KEY,
    route_id VARCHAR(10) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    message TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL,
    anomaly_score FLOAT NOT NULL
);

-- Create index for alerts
CREATE INDEX IF NOT EXISTS idx_alerts_route_id ON alerts (route_id);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts (timestamp);

-- Create table for station information
CREATE TABLE IF NOT EXISTS stations (
    stop_id VARCHAR(20) PRIMARY KEY,
    station_name VARCHAR(100) NOT NULL,
    latitude FLOAT NOT NULL,
    longitude FLOAT NOT NULL
);

-- Create table for route information
CREATE TABLE IF NOT EXISTS routes (
    route_id VARCHAR(10) PRIMARY KEY,
    route_name VARCHAR(100) NOT NULL,
    route_color VARCHAR(7) NOT NULL
);

-- Insert some common NYC subway routes
INSERT INTO routes (route_id, route_name, route_color)
VALUES 
    ('1', '1 Train', '#EE352E'),
    ('2', '2 Train', '#EE352E'),
    ('3', '3 Train', '#EE352E'),
    ('4', '4 Train', '#00933C'),
    ('5', '5 Train', '#00933C'),
    ('6', '6 Train', '#00933C'),
    ('7', '7 Train', '#B933AD'),
    ('A', 'A Train', '#2850AD'),
    ('C', 'C Train', '#2850AD'),
    ('E', 'E Train', '#2850AD'),
    ('B', 'B Train', '#FF6319'),
    ('D', 'D Train', '#FF6319'),
    ('F', 'F Train', '#FF6319'),
    ('M', 'M Train', '#FF6319'),
    ('G', 'G Train', '#6CBE45'),
    ('J', 'J Train', '#996633'),
    ('Z', 'Z Train', '#996633'),
    ('L', 'L Train', '#A7A9AC'),
    ('N', 'N Train', '#FCCC0A'),
    ('Q', 'Q Train', '#FCCC0A'),
    ('R', 'R Train', '#FCCC0A'),
    ('W', 'W Train', '#FCCC0A'),
    ('S', 'S Train', '#808183')
ON CONFLICT (route_id) DO NOTHING;
