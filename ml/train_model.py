"""
Model Training Pipeline with MLflow Experiment Tracking
Supports multiple algorithms: Prophet, LSTM, XGBoost
"""
import mlflow
import mlflow.sklearn
from prophet import Prophet
import pandas as pd
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, mean_absolute_percentage_error
from sklearn.model_selection import TimeSeriesSplit
from feature_engineering import FeatureEngineer
import pickle
import os
import psycopg2
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

class DemandForecaster:
    def __init__(self, db_config, mlflow_uri="http://mlflow:5000"):
        self.fe = FeatureEngineer(db_config)
        self.db_config = db_config
        mlflow.set_tracking_uri(mlflow_uri)
        mlflow.set_experiment("grocery-demand-forecasting")
    
    def train_prophet_model(self, product_name, test_size=0.2, forecast_days=7):
        """
        Train Prophet model for time-series forecasting
        """
        with mlflow.start_run(run_name=f"prophet_{product_name}_{datetime.now().strftime('%Y%m%d')}"):
            # Log parameters
            mlflow.log_param("product", product_name)
            mlflow.log_param("algorithm", "Prophet")
            mlflow.log_param("forecast_horizon", forecast_days)
            mlflow.log_param("test_size", test_size)
            
            # Extract features
            df = self.fe.extract_features(product_name, lookback_days=90)
            
            if df is None or len(df) < 21:
                print(f"❌ Insufficient data for {product_name} (need 21+ days)")
                return None
            
            mlflow.log_param("training_samples", len(df))
            
            # Prepare Prophet format
            prophet_df = df[['order_date', 'quantity']].rename(
                columns={'order_date': 'ds', 'quantity': 'y'}
            )
            
            # Train-test split (time-series split)
            split_idx = int(len(prophet_df) * (1 - test_size))
            train_df = prophet_df[:split_idx]
            test_df = prophet_df[split_idx:]
            
            print(f"📊 Training samples: {len(train_df)}, Test samples: {len(test_df)}")
            
            # Train Prophet model
            model = Prophet(
                daily_seasonality=False,
                weekly_seasonality=True,
                yearly_seasonality=False,
                changepoint_prior_scale=0.05,
                seasonality_prior_scale=10.0,
                interval_width=0.95
            )
            
            model.fit(train_df)
            
            # Evaluate on test set
            if len(test_df) > 0:
                forecast = model.predict(test_df[['ds']])
                predictions = forecast['yhat'].values
                actuals = test_df['y'].values
                
                # Clip negative predictions
                predictions = np.maximum(predictions, 0)
                
                # Calculate metrics
                mae = mean_absolute_error(actuals, predictions)
                rmse = np.sqrt(mean_squared_error(actuals, predictions))
                
                # Avoid division by zero in MAPE
                mape = np.mean(np.abs((actuals - predictions) / (actuals + 1))) * 100
                
                # R-squared
                ss_res = np.sum((actuals - predictions) ** 2)
                ss_tot = np.sum((actuals - np.mean(actuals)) ** 2)
                r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
                
                # Log metrics to MLflow
                mlflow.log_metric("mae", mae)
                mlflow.log_metric("rmse", rmse)
                mlflow.log_metric("mape", mape)
                mlflow.log_metric("r2_score", r2)
                
                print(f"✅ {product_name} Metrics:")
                print(f"   MAE: {mae:.2f}")
                print(f"   RMSE: {rmse:.2f}")
                print(f"   MAPE: {mape:.2f}%")
                print(f"   R²: {r2:.3f}")
                
                # Save metrics to database
                self.save_metrics_to_db(product_name, {
                    'mae': mae,
                    'rmse': rmse,
                    'mape': mape,
                    'r2': r2
                })
            
            # Generate future forecast
            future = model.make_future_dataframe(periods=forecast_days)
            forecast = model.predict(future)
            
            # Save model
            model_path = f"models/{product_name.replace(' ', '_').replace('/', '_')}_prophet.pkl"
            os.makedirs("models", exist_ok=True)
            
            with open(model_path, 'wb') as f:
                pickle.dump(model, f)
            
            mlflow.log_artifact(model_path)
            
            # Log forecast visualization
            try:
                fig = model.plot(forecast)
                fig_path = f"forecast_{product_name.replace(' ', '_')}.png"
                fig.savefig(fig_path)
                mlflow.log_artifact(fig_path)
                os.remove(fig_path)
            except Exception as e:
                print(f"⚠️ Could not save plot: {e}")
            
            return model, forecast
    
    def save_metrics_to_db(self, product_name, metrics):
        """Save model metrics to database for monitoring"""
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        
        for metric_name, metric_value in metrics.items():
            cursor.execute("""
                INSERT INTO model_metrics (product_name, metric_name, metric_value)
                VALUES (%s, %s, %s)
            """, (product_name, metric_name, float(metric_value)))
        
        conn.commit()
        cursor.close()
        conn.close()
    
    def train_all_products(self):
        """Train models for all products with sufficient data"""
        products = self.fe.get_all_products()
        
        print(f"\n{'='*70}")
        print(f"🚀 Starting training for {len(products)} products")
        print(f"{'='*70}\n")
        
        models = {}
        successful = 0
        failed = 0
        
        for i, product in enumerate(products, 1):
            print(f"\n[{i}/{len(products)}] Training model for: {product}")
            try:
                model, forecast = self.train_prophet_model(product)
                if model:
                    models[product] = model
                    successful += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"❌ Error training {product}: {e}")
                failed += 1
        
        print(f"\n{'='*70}")
        print(f"✅ Training Complete!")
        print(f"   Successful: {successful}")
        print(f"   Failed: {failed}")
        print(f"{'='*70}\n")
        
        return models
    
    def close(self):
        self.fe.close()


if __name__ == "__main__":
    import sys
    
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'inventorydb'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres')
    }
    
    mlflow_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://localhost:5000')
    
    forecaster = DemandForecaster(db_config, mlflow_uri)
    
    # Train specific product or all products
    if len(sys.argv) > 1 and sys.argv[1] == '--product':
        product = sys.argv[2]
        model, forecast = forecaster.train_prophet_model(product)
    else:
        models = forecaster.train_all_products()
    
    forecaster.close()
