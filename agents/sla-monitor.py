import json
import time
import redis
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
SLA_TIMEOUT_SECONDS = 180  # 3 minutes
SCAN_BATCH_SIZE = 100
CHECK_INTERVAL = 10  # seconds


def check_sla_breaches():
    """Continuously monitors Redis for unresolved incidents that breach the SLA."""
    
    print("⏳ SLA Monitor: Online. Checking every 10 seconds...")

    # ✅ Safe Redis connection
    try:
        cache: redis.Redis = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            decode_responses=True,
            socket_timeout=5,
          #  retry_on_timeout=True
        )
        cache.ping()
    except redis.ConnectionError:
        print("❌ Redis connection failed. SLA Monitor exiting.")
        return

    while True:
        try:
            cursor = 0

            # ✅ Use SCAN instead of KEYS (non-blocking)
            while True:
                cursor, keys = cache.scan( # type: ignore
                    cursor=cursor,
                    match="audit_trail:*",
                    count=SCAN_BATCH_SIZE
                )

                for key in keys:
                    try:
                        incident_id = key.split(":", 1)[1]

                        # ✅ Fetch logs
                        logs_raw = cache.lrange(key, 0, -1)
                        if not logs_raw:
                            continue

                        logs_parsed = []
                        for log_entry in logs_raw: # type: ignore
                            try:
                                logs_parsed.append(json.loads(log_entry))
                            except (json.JSONDecodeError, TypeError):
                                continue  # ignore bad logs

                        if not logs_parsed:
                            continue

                        # ✅ Logs already ordered (LPUSH → newest first)
                        logs_parsed.reverse()  # oldest → newest

                        # ✅ Get start time safely
                        start_time = logs_parsed[0].get("timestamp")
                        if not start_time:
                            continue

                        resolved = False
                        escalated = False

                        for log in logs_parsed:
                            action = log.get("action")

                            if action == "INCIDENT_VERIFIED":
                                resolved = True
                                break

                            if action in [
                                "ESCALATED_TO_HUMAN",
                                "EXECUTION_FAILED_ESCALATED"
                            ]:
                                escalated = True

                        # ✅ Skip already handled incidents
                        if resolved or escalated:
                            continue

                        # ✅ SLA check
                        elapsed = time.time() - start_time

                        if elapsed > SLA_TIMEOUT_SECONDS:
                            print(f"⚠️ SLA BREACH DETECTED: {incident_id} ({int(elapsed)}s)")

                            escalation_log = {
                                "timestamp": time.time(),
                                "agent": "SLA Monitor",
                                "action": "ESCALATED_TO_HUMAN",
                                "reason": f"SLA Timeout ({SLA_TIMEOUT_SECONDS}s) breached."
                            }

                            # ✅ Push escalation (prevents repeat due to check above)
                            cache.lpush(key, json.dumps(escalation_log))

                            print(f"📣 Alert triggered for {incident_id}")

                    except Exception as inner_error:
                        print(f"⚠️ Error processing key {key}: {inner_error}")

                # Exit scan loop
                if cursor == 0:
                    break

        except Exception as e:
            print(f"❌ Error in SLA monitor loop: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    check_sla_breaches()