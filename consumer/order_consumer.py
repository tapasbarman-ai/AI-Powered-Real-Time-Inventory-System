from kafka import KafkaConsumer
import psycopg2
import json

# PostgreSQL connection
conn = psycopg2.connect(
    dbname="inventorydb",
    user="postgres",
    password="postgres",
    host="localhost",
    port="5432"
)
cursor = conn.cursor()

# Kafka consumer
consumer = KafkaConsumer(
    'order-events',
    bootstrap_servers='localhost:9092',
    auto_offset_reset='earliest',
    enable_auto_commit=True,
    group_id='inventory-group',
    value_deserializer=lambda x: json.loads(x.decode('utf-8'))
)

for msg in consumer:
    order = msg.value
    print("🛒 Consumed ORDER:", order)

    # Update stock table
    cursor.execute("""
        UPDATE stock
        SET quantity = GREATEST(quantity - %s, 0)
        WHERE product_name = %s
    """, (order['quantity'], order['product_name']))

    # Insert into order history table
    cursor.execute("""
        INSERT INTO orders (product_name, quantity, order_time)
        VALUES (%s, %s, to_timestamp(%s))
    """, (order['product_name'], order['quantity'], order['timestamp']))

    if cursor.rowcount == 0:
        print(f"⚠️ No matching product found for: {order['product_name']}")
    else:
        print(f"✅ Updated stock and logged order for: {order['product_name']}")

    conn.commit()
