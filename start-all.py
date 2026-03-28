import subprocess
import sys
import time

def start_swarm():
    print("🚀 Booting up the Multi-Agent SRE Swarm...")
    
    # 1. Start the Streamlit Dashboard
    print("📊 Starting Streamlit Dashboard...")
    subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "dashboard.py"],
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    time.sleep(2) # Give dashboard a head start
    
    # 2. List of background agents to keep running
    agents = [
        "agents/orchestrator-agent.py",
        "agents/execution-agent.py",
        "agents/verifier-agent.py",
        "agents/sla-monitor.py",
        "agents/reporting-agent.py",
        "agents/predictive-agent.py"
    ]
    
    # 3. Start each agent in its own separate terminal window
    for agent in agents:
        print(f"🤖 Starting {agent}...")
        subprocess.Popen(
            [sys.executable, agent],
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        time.sleep(1) # Slight stagger to prevent DB connection spikes
        
    print("\n✅ All agents are online in separate windows!")
    print("💡 Note: You can still run `python agents/diagnostic-agent.py` manually whenever you want to trigger a new incident.")

if __name__ == "__main__":
    start_swarm()
