from kafka import KafkaProducer
import json, random, time

PRODUCTS = [
    "Basmati Rice", "Toor Dal", "Sunflower Oil", "Wheat Flour (Atta)",
    "Milk (500ml Pack)", "Bread (Brown/White)", "Eggs (6/12 pack)",
    "Toothpaste", "Bathing Soap", "Maggi Noodles"
]

import os

producer = KafkaProducer(
    bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092'),
    value_serializer=lambda x: json.dumps(x).encode('utf-8')
)

while True:
    order = {
        "product_name": random.choice(PRODUCTS),
        "quantity": random.randint(1, 5),
        "timestamp": time.time()
    }
    producer.send('order-events', value=order)
    print("Produced ORDER:", order)
    time.sleep(2)