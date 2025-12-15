from kafka import KafkaConsumer
import psycopg2
import json
import requests
from datetime import datetime, timedelta

class MLEnabledConsumer:
    def __init__(self):
        # PostgreSQL connection
        self.conn = psycopg2.connect(
            dbname="inventorydb",
            user="postgres",
            password="postgres",
            host="postgres",  # Use service name in Docker
            port="5432"
        )
        self.cursor = self.conn.cursor()
        
        # Kafka consumer
        self.consumer = KafkaConsumer(
            'order-events',
            bootstrap_servers='kafka:9092',
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            group_id='inventory-group',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        
        self.prediction_service_url = "http://prediction-service:8000"
    
    def check_low_stock_alert(self, product_name, current_quantity):
        """Check if stock is low and get recommendations"""
        if current_quantity < 20:  # Low stock threshold
            try:
                # Get 7-day demand forecast
                response = requests.post(
                    f"{self.prediction_service_url}/forecast",
                    json={"product_name": product_name, "days": 7},
                    timeout=2
                )
                
                if response.status_code == 200:
                    forecast = response.json()
                    recommended = forecast['recommended_reorder']
                    
                    if recommended > 0:
                        # Determine urgency
                        urgency = 'critical' if current_quantity < 10 else 'high'
                        
                        # Insert reorder recommendation
                        self.cursor.execute("""
                            INSERT INTO reorder_recommendations 
                            (product_name, recommended_quantity, urgency_level, reason)
                            VALUES (%s, %s, %s, %s)
                        """, (
                            product_name, 
                            recommended,
                            urgency,
                            f"Current stock: {current_quantity}, Predicted 7-day demand: {sum([f['predicted_demand'] for f in forecast['forecasts']])}"
                        ))
                        
                        print(f"🔔 ALERT: {product_name} - Recommend ordering {recommended} units")
            except Exception as e:
                print(f"⚠️ Could not fetch forecast: {e}")
    
    def consume_orders(self):
        """Main consumption loop"""
        print("🚀 ML-Enhanced Consumer started...")
        
        for msg in self.consumer:
            order = msg.value
            print(f"🛒 Consumed ORDER: {order}")
            
            try:
                # Update stock table
                self.cursor.execute("""
                    UPDATE stock
                    SET quantity = GREATEST(quantity - %s, 0),
                        last_updated = NOW()
                    WHERE product_name = %s
                    RETURNING quantity
                """, (order['quantity'], order['product_name']))
                
                result = self.cursor.fetchone()
                
                if result:
                    new_quantity = result[0]
                    print(f"✅ Updated {order['product_name']}: New stock = {new_quantity}")
                    
                    # Insert into order history
                    self.cursor.execute("""
                        INSERT INTO orders (product_name, quantity, order_time)
                        VALUES (%s, %s, to_timestamp(%s))
                    """, (order['product_name'], order['quantity'], order['timestamp']))
                    
                    # Check for low stock and trigger alerts
                    self.check_low_stock_alert(order['product_name'], new_quantity)
                    
                    self.conn.commit()
                else:
                    print(f"⚠️ No matching product: {order['product_name']}")
                    
            except Exception as e:
                print(f"❌ Error processing order: {e}")
                self.conn.rollback()
    
    def close(self):
        self.cursor.close()
        self.conn.close()
        self.consumer.close()

if __name__ == "__main__":
    consumer = MLEnabledConsumer()
    try:
        consumer.consume_orders()
    except KeyboardInterrupt:
        print("\n⏹️ Shutting down consumer...")
    finally:
        consumer.close()
