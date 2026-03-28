import paramiko
import json
import time
import os
from kafka import KafkaConsumer, KafkaProducer
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
EC2_IP = os.getenv("EC2_IP", "51.20.54.47")
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH", "hackathon-agent-key.pem")
SSH_USER = os.getenv("SSH_USER", "ec2-user")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")

def execute_remote_command(command):
    """Connects to the server and executes the remediation command."""
    print(f"🛠️ Execution Agent: Establishing secure SSH connection to target...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(hostname=EC2_IP, username=SSH_USER, key_filename=SSH_KEY_PATH)
        print(f"⚡ Executing system command: {command}")
        
        # Execute the command
        stdin, stdout, stderr = ssh.exec_command(command)
        
        # Read the output/errors to ensure it worked
        error = stderr.read().decode('utf-8')
        output = stdout.read().decode('utf-8')
        ssh.close()
        
        if error and "Warning" not in error:
            print(f"⚠️ Command executed with errors: {error}")
            return False, error
            
        print(f"✅ Target neutralized successfully. Output: {output}")
        return True, output
        
    except Exception as e:
        print(f"❌ Execution failed: {e}")
        return False, str(e)

def start_execution_agent():
    print("🦾 Execution Agent is online and awaiting commands...")
    
    # Listen to the Orchestrator
    consumer = KafkaConsumer(
        'execute-command',
        bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        auto_offset_reset='latest'
    )
    
    # Talk to the Verifier & Orchestrator (for failure feedback loops)
    producer = KafkaProducer(
        bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    for message in consumer:
        payload = message.value
        incident_id = payload.get("incident_id")
        command = payload.get("command")
        
        print(f"\n🚨 Action Required for {incident_id}: {command}")
        
        # Start the clock for the financial savings calculation
        start_time = time.time()
        
        # 1. DO THE WORK
        success, details = execute_remote_command(command)
        
        # Stop the clock
        resolution_time = time.time() - start_time
        
        # 2. REPORT THE SUCCESS OR FAILURE
        if success:
            resolution_payload = {
                "incident_id": incident_id,
                "status": "RESOLVED",
                "resolution_time_seconds": round(resolution_time, 2)
            }
            print("📡 Publishing resolution status to Verifier...")
            producer.send('verification-status', resolution_payload)
        else:
            failure_payload = {
                "incident_id": incident_id,
                "status": "FAILED",
                "error_reason": details,
                "failed_command": command
            }
            print("🛑 Publishing failure feedback to Orchestrator...")
            producer.send('execution-feedback', failure_payload)
            
        producer.flush()

if __name__ == "__main__":
    start_execution_agent()