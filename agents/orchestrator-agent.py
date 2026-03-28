import json
import time
import redis
import os
from kafka import KafkaConsumer, KafkaProducer
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")

# --- Enterprise Guardrails ---
# Ensure AI is only running safe commands.
ALLOWED_COMMAND_PREFIXES = [
    "kill -9", 
    "sudo systemctl restart", 
    "sudo systemctl stop",
    "rm -rf /tmp/", 
    "sudo apt-get clean",
    "docker system prune"
]

def validate_and_create_plan(diagnosis):
    """Checks the AI diagnosis against enterprise rules and creates a strict execution plan."""
    incident_id = diagnosis.get("incident_id")
    recommended_command = diagnosis.get("recommended_command", "").strip()
    issue_type = diagnosis.get("issue_type", "unknown")
    
    # 1. Check the Guardrails
    is_safe = any(recommended_command.startswith(prefix) for prefix in ALLOWED_COMMAND_PREFIXES)
    
    if not is_safe:
        return {
            "incident_id": incident_id,
            "status": "ESCALATED",
            "reason": f"Guardrail trigger: Command '{recommended_command}' is not in the safe whitelist. Escalating to human."
        }
        
    # 2. Formulate the Execution Command
    return {
        "incident_id": incident_id,
        "action": "execute_ssh_command",
        "command": recommended_command,
        "target": diagnosis.get("target"),
        "status": "APPROVED",
        "issue_type": issue_type
    }

def start_orchestrator():
    print("🧠 Orchestrator Agent is online and applying guardrails...")
    
    # Connect to Redis for the Audit Trail
    cache = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    
    # Listen to the Diagnostic Agent & Execution Agent feedback
    consumer = KafkaConsumer(
        bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        auto_offset_reset='latest'
    )
    consumer.subscribe(['remediation-plan', 'execution-feedback'])
    
    # Talk to the Execution Agent
    producer = KafkaProducer(
        bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    print("🎧 Listening for new diagnoses and feedback loops...")

    for message in consumer:
        if message.topic == 'remediation-plan':
            diagnosis = message.value
            incident_id = diagnosis.get("incident_id")
            print(f"\n🚨 Received diagnosis for {incident_id}: {diagnosis.get('reason')}")
            
            # Log receipt to audit trail
            cache.lpush(f"audit_trail:{incident_id}", json.dumps({
                "timestamp": time.time(), "agent": "Orchestrator", "action": "DIAGNOSIS_RECEIVED", "data": diagnosis
            }))
            
            # Apply Guardrails
            execution_plan = validate_and_create_plan(diagnosis)
            
            if execution_plan["status"] == "APPROVED":
                print(f"✅ Guardrails passed. Issuing command: {execution_plan['command']}")
                
                # Send to Execution Agent
                producer.send('execute-command', execution_plan)
                producer.flush()
                
                # Log approval to audit trail
                cache.lpush(f"audit_trail:{incident_id}", json.dumps({
                    "timestamp": time.time(), "agent": "Orchestrator", "action": "PLAN_APPROVED", "data": execution_plan
                }))
            else:
                print(f"🛑 GUARDRAIL BLOCKED: {execution_plan['reason']}")
                # Log escalation
                cache.lpush(f"audit_trail:{incident_id}", json.dumps({
                    "timestamp": time.time(), "agent": "Orchestrator", "action": "ESCALATED_TO_HUMAN", "data": execution_plan
                }))
                
        elif message.topic == 'execution-feedback':
            feedback = message.value
            incident_id = feedback.get("incident_id")
            print(f"\n🔄 SELF-CORRECTION TRIGGERED for {incident_id}: Action failed -> {feedback.get('error_reason')}")
            
            # Self-correction: Escalating immediately since the approved action failed
            escalation_payload = {
                "incident_id": incident_id,
                "status": "ESCALATED",
                "reason": f"Execution failed for command {feedback.get('failed_command')}. Error: {feedback.get('error_reason')}"
            }
            
            cache.lpush(f"audit_trail:{incident_id}", json.dumps({
                "timestamp": time.time(), "agent": "Orchestrator", "action": "EXECUTION_FAILED_ESCALATED", "data": escalation_payload
            }))
            print(f"📣 Sent Escelation alert to human for {incident_id}")

if __name__ == "__main__":
    start_orchestrator()