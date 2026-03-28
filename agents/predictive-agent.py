import paramiko
import os
import json
import time
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

def get_predictive_metrics():
    """Pulls metrics geared towards trend analysis and early warnings."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(hostname=EC2_IP, username=SSH_USER, key_filename=SSH_KEY_PATH)
        # Uptime (load average), memory usage, and disk space
        command = (
            "echo '--- LOAD AVERAGE ---'; uptime; "
            "echo '--- MEMORY USAGE ---'; free -m; "
            "echo '--- DISK USAGE ---'; df -h | grep -v 'loop'; "
            "echo '--- TOP HOGS ---'; ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%mem | head -n 5"
        )
        stdin, stdout, stderr = ssh.exec_command(command)
        data = stdout.read().decode('utf-8')
        ssh.close()
        return data
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None

def analyze_preventative_actions(data):
    """Uses Groq to spot early-stage anomalies."""
    client = Groq(api_key=GROQ_API_KEY)
    
    prompt = f"""
    You are a Predictive SRE AI. Your job is to catch issues BEFORE they cause downtime.
    Analyze the server metrics below. Look for early warning signs:
    - High load averages growing.
    - Disk usage above 80% (needs cleanup before it hits 100%).
    
    If the system is completely healthy and under normal thresholds, return exactly: {{"status": "healthy"}}
    
    If you detect an EARLY WARNING, issue a preventative maintenance plan.
    Reply ONLY with a JSON object containing:
    - 'incident_id' (e.g., 'PREV-901')
    - 'issue_type' (e.g., 'predictive_disk_cleanup', 'predictive_memory_release')
    - 'target' (e.g., 'cache', 'logs')
    - 'recommended_command' (MUST start with one of our whitelisted commands: 'rm -rf /tmp/', 'sudo apt-get clean', 'docker system prune', 'sudo systemctl restart')
    - 'reason' (explain why doing this now prevents a future outage)
    
    Server Data:
    {data}
    """
    
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant", 
        response_format={"type": "json_object"}
    )
    
    content = response.choices[0].message.content
    if content is None:
        return {"status": "healthy"}
    return json.loads(content)

def start_predictive_agent():
    print("🔮 Predictive Agent is online... Scanning for early warnings every 45 seconds.")
    producer = KafkaProducer(
        bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    
    while True:
        try:
            metrics = get_predictive_metrics()
            if metrics:
                analysis = analyze_preventative_actions(metrics)
                
                if analysis.get("status") == "healthy":
                    print("✅ System is stable. No preventative action needed.")
                else:
                    print(f"⚠️ Anomaly Predicted! Initiating Preventative Action: {analysis.get('reason')}")
                    # Push PREVENTATIVE action to the exact same pipeline the Orchestrator reads
                    analysis["is_predictive"] = "true"  # using string to satisfy strict typing
                    producer.send('remediation-plan', analysis)
                    producer.flush()
            
            # Wait 45 seconds before checking again
            time.sleep(45)
        except Exception as e:
            print(f"Error in predictive loop: {e}")
            time.sleep(45)

if __name__ == "__main__":
    start_predictive_agent()
