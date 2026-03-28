import json
import time
import redis
import os
from kafka import KafkaConsumer, errors as kafka_errors
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
COST_PER_MINUTE_DOWNTIME = 150.00
AVERAGE_MANUAL_FIX_TIME_MINUTES = 15.0
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")


def calculate_savings(autonomous_resolution_time_seconds):
    """Calculate money saved."""
    autonomous_time_minutes = autonomous_resolution_time_seconds / 60.0
    time_saved = AVERAGE_MANUAL_FIX_TIME_MINUTES - autonomous_time_minutes

    if time_saved > 0:
        return round(time_saved * COST_PER_MINUTE_DOWNTIME, 2)
    return 0.0


def connect_redis():
    """Safe Redis connection."""
    try:
        cache = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        cache.ping()
        print("✅ Connected to Redis")
        return cache
    except redis.ConnectionError:
        print("❌ Redis connection failed. Make sure Redis is running.")
        exit(1)


def connect_kafka():
    """Safe Kafka connection."""
    try:
        consumer = KafkaConsumer(
            'verification-status',
            bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            auto_offset_reset='latest',
            group_id='verifier-group',   # IMPORTANT
            enable_auto_commit=True
        )
        print("✅ Connected to Kafka")
        return consumer
    except kafka_errors.KafkaError as e:
        print(f"❌ Kafka connection failed: {e}")
        exit(1)


def start_verifier():
    print("🚀 Verifier Agent (Financial Quantifier) is online...")

    cache = connect_redis()

    # Initialize total savings safely
    if not cache.exists("total_dollars_saved"):
        cache.set("total_dollars_saved", "0.0")

    consumer = connect_kafka()

    print("📡 Listening for resolved incidents...")

    try:
        for message in consumer:
            try:
                payload = message.value

                incident_id = payload.get("incident_id")
                status = payload.get("status")
                resolution_time_sec = payload.get("resolution_time_seconds", 0)

                if not incident_id:
                    print("⚠️ Skipping invalid message (missing incident_id)")
                    continue

                if status == "RESOLVED":
                    print(f"\n✅ Incident {incident_id} resolved!")

                    money_saved = calculate_savings(resolution_time_sec)

                    # Safe Redis read
                    raw_total = cache.get("total_dollars_saved")
                    if isinstance(raw_total, bytes):
                        current_total = float(raw_total.decode("utf-8"))
                    elif isinstance(raw_total, (str, int, float)):
                        current_total = float(raw_total)
                    else:
                        current_total = 0.0

                    new_total = current_total + money_saved
                    cache.set("total_dollars_saved", str(new_total))

                    # Audit log
                    audit_log = {
                        "timestamp": time.time(),
                        "action": "INCIDENT_VERIFIED",
                        "autonomous_time_sec": resolution_time_sec,
                        "dollars_saved": money_saved
                    }

                    cache.lpush(
                        f"audit_trail:{incident_id}",
                        json.dumps(audit_log)
                    )

                    print(f"💰 Saved: ${money_saved}")
                    print(f"📊 Total Savings: ${new_total}")

            except Exception as e:
                print(f"⚠️ Error processing message: {e}")

    except KeyboardInterrupt:
        print("\n🛑 Shutting down verifier...")

    finally:
        consumer.close()
        print("👋 Kafka consumer closed")


if __name__ == "__main__":
    start_verifier()