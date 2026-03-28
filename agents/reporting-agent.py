import json
import time
import redis
import os
from kafka import KafkaConsumer
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def generate_rca_report(incident_id, logs, client):
    print(f"📝 Reporting Agent: Generating RCA for {incident_id}...")
    
    # Format the timeline into a readable string
    timeline = "\n".join([f"[{log.get('agent', 'System')}] Action: {log.get('action')} | Data: {json.dumps(log.get('data', {}))}" for log in logs])
    
    prompt = f"""
    You are an expert Enterprise Site Reliability Engineer. A production incident was just resolved autonomously by our multi-agent system.
    Please write a professional "Post-Mortem Root Cause Analysis" (RCA) using Markdown format. 

    Include the following sections:
    - Incident Overview
    - Root Cause Analysis
    - Remediation Steps Taken (by the AI)
    - Future Preventative Measures

    Here is the exact timeline of actions taken by our agents during the incident:
    {timeline}
    """
    
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant"
    )
    
    return response.choices[0].message.content

def start_reporting_agent():
    print("📝 Reporting Agent is online... Waiting for resolved incidents.")
    
    # Connect to Redis
    try:
        cache = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        cache.ping()
    except redis.ConnectionError:
        print("❌ Redis connection failed.")
        return

    # Kafka Consumer
    consumer = KafkaConsumer(
        'verification-status',
        bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        auto_offset_reset='latest',
        group_id='reporting-group'
    )
    
    groq_client = Groq(api_key=GROQ_API_KEY)

    for message in consumer:
        payload = message.value
        incident_id = payload.get("incident_id")
        status = payload.get("status")

        if status == "RESOLVED":
            # 1. Fetch the full audit trail for the LLM context
            raw_logs = cache.lrange(f"audit_trail:{incident_id}", 0, -1)
            
            parsed_logs = []
            for log in raw_logs: # type: ignore
                try: parsed_logs.append(json.loads(log))
                except (json.JSONDecodeError, TypeError): pass
            
            parsed_logs.reverse() # Oldest to newest
            
            # 2. Ask Groq for the Markdown RCA
            rca_markdown = generate_rca_report(incident_id, parsed_logs, groq_client)
            
            # 3. Save the actual markdown back into the Redis log stream
            rca_log = {
                "timestamp": time.time(),
                "agent": "Reporting Agent",
                "action": "POST_MORTEM_GENERATED",
                "data": {"rca_markdown": rca_markdown}
            }
            cache.lpush(f"audit_trail:{incident_id}", json.dumps(rca_log))
            print(f"✅ Generated and attached RCA Post-Mortem for {incident_id}")

if __name__ == "__main__":
    start_reporting_agent()