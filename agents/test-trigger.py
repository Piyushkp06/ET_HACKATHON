from kafka import KafkaProducer
import json
import os
from dotenv import load_dotenv

load_dotenv()

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")

print("🔌 Connecting to Kafka...")
producer = KafkaProducer(
    bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# This is the exact payload your Execution Agent will send when it finishes a job
dummy_payload = {
    "incident_id": "INC-001",
    "status": "RESOLVED",
    "resolution_time_seconds": 120  # Took the AI 2 minutes to fix
}

print(f"🚀 Firing dummy resolution event: {dummy_payload}")
producer.send('verification-status', dummy_payload)
producer.flush() # Ensure the message goes through immediately

print("✅ Message sent successfully!")