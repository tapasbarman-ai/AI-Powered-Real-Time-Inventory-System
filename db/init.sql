-- 🛒 Existing tables (keep as is)
CREATE TABLE IF NOT EXISTS stock (
    product_id SERIAL PRIMARY KEY,
    product_name TEXT UNIQUE,
    quantity INT DEFAULT 100,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    order_id SERIAL PRIMARY KEY,
    product_name TEXT,
    quantity INT,
    order_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 🤖 NEW: ML Predictions tracking
CREATE TABLE IF NOT EXISTS ml_predictions (
    id SERIAL PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    prediction_date DATE NOT NULL,
    predicted_demand INTEGER NOT NULL,
    confidence_lower INTEGER,
    confidence_upper INTEGER,
    model_version VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(product_name, prediction_date)
);

-- 📊 NEW: Model performance metrics
CREATE TABLE IF NOT EXISTS model_metrics (
    id SERIAL PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    metric_name VARCHAR(50) NOT NULL,
    metric_value FLOAT NOT NULL,
    evaluation_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 🔔 NEW: Reorder recommendations
CREATE TABLE IF NOT EXISTS reorder_recommendations (
    id SERIAL PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    recommended_quantity INTEGER NOT NULL,
    urgency_level VARCHAR(20), -- 'low', 'medium', 'high', 'critical'
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending' -- 'pending', 'approved', 'ordered'
);

-- 🎯 NEW: A/B test experiments
CREATE TABLE IF NOT EXISTS ab_experiments (
    id SERIAL PRIMARY KEY,
    experiment_name VARCHAR(100),
    product_name VARCHAR(255),
    model_version VARCHAR(50),
    prediction_value INTEGER,
    actual_value INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_orders_product_time ON orders(product_name, order_time);
CREATE INDEX IF NOT EXISTS idx_predictions_product_date ON ml_predictions(product_name, prediction_date);
CREATE INDEX IF NOT EXISTS idx_metrics_product ON model_metrics(product_name, evaluation_date);

-- 🌱 Seed Data
INSERT INTO stock (product_name, quantity) VALUES
('Basmati Rice', 100),
('Toor Dal', 100),
('Sunflower Oil', 100),
('Wheat Flour (Atta)', 100),
('Milk (500ml Pack)', 100),
('Bread (Brown/White)', 100),
('Eggs (6/12 pack)', 100),
('Toothpaste', 100),
('Bathing Soap', 100),
('Maggi Noodles', 100)
ON CONFLICT (product_name) DO NOTHING;
