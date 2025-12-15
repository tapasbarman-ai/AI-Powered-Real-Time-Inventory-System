"""
Model Monitoring and Performance Tracking
Compares predictions vs actuals, detects drift, triggers retraining
"""
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
import mlflow
import schedule
import time
import os

class ModelMonitor:
    def __init__(self, db_config, mlflow_uri="http://mlflow:5000"):
        self.conn = psycopg2.connect(**db_config)
        self.mlflow_uri = mlflow_uri
        mlflow.set_tracking_uri(mlflow_uri)
        mlflow.set_experiment("model-monitoring")
    
    def evaluate_recent_predictions(self, product_name, days_back=7):
        """
        Compare recent predictions against actual demand
        Returns metrics indicating model performance
        """
        # Get predictions made in the past week
        pred_query = """
        SELECT 
            prediction_date,
            predicted_demand,
            model_version
        FROM ml_predictions
        WHERE product_name = %s
        AND prediction_date >= CURRENT_DATE - INTERVAL '%s days'
        AND prediction_date < CURRENT_DATE
        ORDER BY prediction_date
        """
        
        # Get actual orders for same period
        actual_query = """
        SELECT 
            DATE(order_time) as order_date,
            SUM(quantity) as actual_demand
        FROM orders
        WHERE product_name = %s
        AND order_time >= CURRENT_DATE - INTERVAL '%s days'
        AND DATE(order_time) < CURRENT_DATE
        GROUP BY DATE(order_time)
        ORDER BY order_date
        """
        
        try:
            pred_df = pd.read_sql(pred_query, self.conn, params=(product_name, days_back))
            actual_df = pd.read_sql(actual_query, self.conn, params=(product_name, days_back))
            
            if pred_df.empty or actual_df.empty:
                return None
            
            # Merge predictions with actuals
            merged = pd.merge(
                pred_df,
                actual_df,
                left_on='prediction_date',
                right_on='order_date',
                how='inner'
            )
            
            if len(merged) < 3:
                print(f"⚠️ Insufficient matched data for {product_name}")
                return None
            
            # Calculate performance metrics
            predictions = merged['predicted_demand'].values
            actuals = merged['actual_demand'].values
            
            mae = mean_absolute_error(actuals, predictions)
            rmse = np.sqrt(np.mean((predictions - actuals) ** 2))
            mape = np.mean(np.abs((actuals - predictions) / (actuals + 1))) * 100
            
            # Bias (are we over or under predicting?)
            bias = np.mean(predictions - actuals)
            
            # Get baseline metrics from training
            baseline_mae = self.get_baseline_metric(product_name, 'mae')
            
            # Detect drift (performance degradation)
            drift_detected = False
            drift_score = 0
            
            if baseline_mae:
                performance_ratio = mae / baseline_mae
                drift_score = (performance_ratio - 1) * 100  # % degradation
                
                # Trigger if 30% worse than baseline
                if performance_ratio > 1.3:
                    drift_detected = True
            
            metrics = {
                'product': product_name,
                'mae': mae,
                'rmse': rmse,
                'mape': mape,
                'bias': bias,
                'baseline_mae': baseline_mae,
                'drift_score': drift_score,
                'drift_detected': drift_detected,
                'samples_evaluated': len(merged)
            }
            
            # Log to MLflow
            with mlflow.start_run(run_name=f"monitor_{product_name}_{datetime.now().strftime('%Y%m%d')}"):
                mlflow.log_param("product", product_name)
                mlflow.log_param("evaluation_days", days_back)
                mlflow.log_metrics({
                    "live_mae": mae,
                    "live_rmse": rmse,
                    "live_mape": mape,
                    "bias": bias,
                    "drift_score": drift_score
                })
                mlflow.set_tag("drift_detected", str(drift_detected))
            
            return metrics
            
        except Exception as e:
            print(f"❌ Error evaluating {product_name}: {e}")
            return None
    
    def get_baseline_metric(self, product_name, metric_name):
        """Retrieve baseline metric from training"""
        query = """
        SELECT metric_value 
        FROM model_metrics
        WHERE product_name = %s 
        AND metric_name = %s
        ORDER BY created_at DESC 
        LIMIT 1
        """
        cursor = self.conn.cursor()
        cursor.execute(query, (product_name, metric_name))
        result = cursor.fetchone()
        return result[0] if result else None
    
    def trigger_retraining(self, product_name, reason):
        """Log retraining request"""
        print(f"\n🔄 RETRAINING TRIGGERED for {product_name}")
        print(f"   Reason: {reason}")
        
        # Log event to MLflow
        with mlflow.start_run(run_name=f"retrain_trigger_{product_name}"):
            mlflow.log_param("product", product_name)
            mlflow.log_param("reason", reason)
            mlflow.log_param("timestamp", datetime.now().isoformat())
            mlflow.set_tag("action", "retrain_triggered")
        
        # In production: trigger Airflow DAG or training job
        # For now, we'll just log it
        # os.system(f"python ml/train_model.py --product '{product_name}'")
    
    def monitor_all_products(self):
        """Monitor all products with predictions"""
        print(f"\n{'='*70}")
        print(f"📊 MODEL MONITORING RUN: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}\n")
        
        # Get products with recent predictions
        query = """
        SELECT DISTINCT product_name
        FROM ml_predictions
        WHERE prediction_date >= CURRENT_DATE - INTERVAL '7 days'
        """
        products_df = pd.read_sql(query, self.conn)
        
        if products_df.empty:
            print("ℹ️ No products with recent predictions to monitor")
            return []
        
        results = []
        drift_count = 0
        
        for product in products_df['product_name']:
            metrics = self.evaluate_recent_predictions(product, days_back=7)
            
            if metrics:
                results.append(metrics)
                
                print(f"\n📦 {metrics['product']}")
                print(f"   MAE: {metrics['mae']:.2f} (Baseline: {metrics['baseline_mae']:.2f if metrics['baseline_mae'] else 'N/A'})")
                print(f"   MAPE: {metrics['mape']:.1f}%")
                print(f"   Bias: {metrics['bias']:+.2f}")
                print(f"   Drift Score: {metrics['drift_score']:+.1f}%")
                print(f"   Status: {'🔴 DRIFT DETECTED' if metrics['drift_detected'] else '🟢 OK'}")
                
                if metrics['drift_detected']:
                    drift_count += 1
                    self.trigger_retraining(
                        product,
                        f"Performance degraded by {metrics['drift_score']:.1f}%"
                    )
        
        print(f"\n{'='*70}")
        print(f"✅ Monitoring Complete")
        print(f"   Products Evaluated: {len(results)}")
        print(f"   Drift Detected: {drift_count}")
        print(f"{'='*70}\n")
        
        return results
    
    def close(self):
        self.conn.close()


def run_scheduled_monitoring():
    """Run monitoring on schedule"""
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'inventorydb'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres')
    }
    
    monitor = ModelMonitor(db_config)
    
    # Schedule daily check
    schedule.every().day.at("00:00").do(monitor.monitor_all_products)
    
    print("⏳ Starting scheduled monitoring service...")
    monitor.monitor_all_products() # Run once on startup
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    run_scheduled_monitoring()
