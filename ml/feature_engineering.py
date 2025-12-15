"""
Feature Engineering for Demand Forecasting
Extracts time-series features from PostgreSQL orders table
"""
import pandas as pd
import psycopg2
import numpy as np
from datetime import datetime, timedelta

class FeatureEngineer:
    def __init__(self, db_config):
        self.conn = psycopg2.connect(**db_config)
    
    def extract_features(self, product_name, lookback_days=60):
        """
        Extract time-series features for a product
        Returns: DataFrame with engineered features
        """
        query = """
        SELECT 
            product_name,
            quantity,
            order_time,
            EXTRACT(DOW FROM order_time) as day_of_week,
            EXTRACT(HOUR FROM order_time) as hour_of_day,
            EXTRACT(DAY FROM order_time) as day_of_month,
            DATE(order_time) as order_date
        FROM orders
        WHERE product_name = %s
        AND order_time >= NOW() - INTERVAL '%s days'
        ORDER BY order_time
        """
        
        df = pd.read_sql(query, self.conn, params=(product_name, lookback_days))
        
        if df.empty:
            print(f"⚠️ No data for {product_name}")
            return None
        
        # Aggregate to daily level
        daily_df = df.groupby('order_date').agg({
            'quantity': 'sum',
            'day_of_week': 'first'
        }).reset_index()
        
        daily_df = daily_df.sort_values('order_date').reset_index(drop=True)
        
        # Time-based features
        daily_df['is_weekend'] = daily_df['day_of_week'].isin([5, 6]).astype(int)
        daily_df['day_of_week'] = daily_df['day_of_week'].astype(int)
        
        # Rolling window statistics (7-day and 14-day)
        daily_df['rolling_mean_7d'] = daily_df['quantity'].rolling(window=7, min_periods=1).mean()
        daily_df['rolling_std_7d'] = daily_df['quantity'].rolling(window=7, min_periods=1).std().fillna(0)
        daily_df['rolling_mean_14d'] = daily_df['quantity'].rolling(window=14, min_periods=1).mean()
        
        # Lag features
        for lag in [1, 2, 7, 14]:
            daily_df[f'lag_{lag}'] = daily_df['quantity'].shift(lag)
        
        # Fill NaN values
        daily_df = daily_df.fillna(0)
        
        # Exponential moving average
        daily_df['ema_7d'] = daily_df['quantity'].ewm(span=7, adjust=False).mean()
        
        # Trend (difference from moving average)
        daily_df['trend'] = daily_df['quantity'] - daily_df['rolling_mean_7d']
        
        return daily_df
    
    def get_all_products(self):
        """Get list of all products with sufficient history"""
        query = """
        SELECT product_name, COUNT(*) as order_count
        FROM orders
        WHERE order_time >= NOW() - INTERVAL '60 days'
        GROUP BY product_name
        HAVING COUNT(*) >= 14
        ORDER BY product_name
        """
        df = pd.read_sql(query, self.conn)
        return df['product_name'].tolist()
    
    def get_product_statistics(self, product_name):
        """Get statistical summary for a product"""
        query = """
        SELECT 
            product_name,
            COUNT(*) as total_orders,
            SUM(quantity) as total_quantity,
            AVG(quantity) as avg_quantity,
            MIN(order_time) as first_order,
            MAX(order_time) as last_order
        FROM orders
        WHERE product_name = %s
        GROUP BY product_name
        """
        df = pd.read_sql(query, self.conn, params=(product_name,))
        return df.iloc[0].to_dict() if not df.empty else None
    
    def close(self):
        self.conn.close()


if __name__ == "__main__":
    # Test feature engineering
    db_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'inventorydb',
        'user': 'postgres',
        'password': 'postgres'
    }
    
    fe = FeatureEngineer(db_config)
    try:
        products = fe.get_all_products()
        print(f"📊 Products with sufficient data: {len(products)}")
        
        for product in products[:3]:  # Show first 3
            print(f"\n{'='*60}")
            print(f"Product: {product}")
            print(f"{'='*60}")
            
            stats = fe.get_product_statistics(product)
            print(f"Total Orders: {stats['total_orders']}")
            print(f"Total Quantity: {stats['total_quantity']}")
            print(f"Avg per Order: {stats['avg_quantity']:.2f}")
            
            features = fe.extract_features(product, lookback_days=30)
            if features is not None:
                print(f"\nFeatures shape: {features.shape}")
                print("\nLast 5 days:")
                print(features[['order_date', 'quantity', 'rolling_mean_7d', 'trend']].tail())
    except Exception as e:
        print(f"Error: {e}")
    finally:
        fe.close()
