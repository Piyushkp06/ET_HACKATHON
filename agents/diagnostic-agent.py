import paramiko
import os
import json
from groq import Groq
from kafka import KafkaProducer
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
EC2_IP = os.getenv("EC2_IP", "51.20.54.47")
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH", "hackathon-agent-key.pem")
SSH_USER = os.getenv("SSH_USER", "ec2-user")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")

def get_system_health():
    """Connects to EC2 and pulls comprehensive system health (CPU, Disk, Services)."""
    print("🤖 Diagnostic Agent: Connecting to target server...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(hostname=EC2_IP, username=SSH_USER, key_filename=SSH_KEY_PATH)
        # Pull process, disk, and service states
        command = (
            "echo '--- TOP PROCESSES ---'; top -b -n 1 | head -n 12; "
            "echo '--- DISK USAGE ---'; df -h | grep -v 'loop'; "
            "echo '--- FAILED SERVICES ---'; systemctl list-units --state=failed --no-pager"
        )
        stdin, stdout, stderr = ssh.exec_command(command)
        process_data = stdout.read().decode('utf-8')
        ssh.close()
        return process_data
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None

def diagnose_issue(process_data):
    """Uses Groq LLM to analyze the processes and find the culprit."""
    print("🧠 Diagnostic Agent: Analyzing system logs with AI...")
    
    # Ensure you have set your GROQ_API_KEY environment variable in your terminal
    client = Groq(api_key=GROQ_API_KEY) 
    
    prompt = f"""
    You are an expert Site Reliability Engineer AI. 
    Analyze the following system health output from a Linux server (includes CPU, Disk, and Failed Services).
    Identify the most critical issue. This might be a rogue high CPU process, disk full, or a crashed service.
    Reply ONLY with a JSON object containing: 
    - 'incident_id' (generate a random string like 'INC-104')
    - 'issue_type' (e.g., 'high_cpu', 'disk_full', 'service_crash')
    - 'target' (e.g., the PID, the mount point, or the service name)
    - 'recommended_command' (the exact safe bash command to fix it, e.g., 'kill -9 <pid>', 'sudo systemctl restart <service>', 'docker system prune', or 'rm -rf /tmp/*')
    - 'reason' (a short explanation of the root cause and why you chose this fix)
    
    Server Data:
    {process_data}
    """
    
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant", 
        response_format={"type": "json_object"}
    )
    
    content = response.choices[0].message.content
    if not isinstance(content, str):
        raise ValueError("No response content from AI model")
    return json.loads(content)

def publish_to_kafka(diagnosis_json):
    """Sends the AI's diagnosis to the Orchestrator via Kafka."""
    print("📡 Diagnostic Agent: Publishing diagnosis to Kafka topic 'remediation-plan'...")
    producer = KafkaProducer(
        bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    
    producer.send('remediation-plan', diagnosis_json)
    producer.flush()
    print("✅ Diagnosis published successfully!")

if __name__ == "__main__":
    # 1. Pull the data
    logs = get_system_health()
    
    if logs:
        print("\n--- Raw Data Pulled from Server ---")
        print(logs)
        
        # 2. Analyze the data
        diagnosis = diagnose_issue(logs)
        print("\n--- AI Diagnosis ---")
        print(json.dumps(diagnosis, indent=2))
        
        # 3. Hand it off to the next agent
        publish_to_kafka(diagnosis)