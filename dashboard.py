import streamlit as st
import redis
import json
import pandas as pd
from datetime import datetime
import time
import plotly.express as px
import os
from dotenv import load_dotenv

load_dotenv()

# --- PAGE CONFIG ---
st.set_page_config(page_title="Autonomic SRE Command Center", page_icon="🧿", layout="wide", initial_sidebar_state="expanded")

# --- CUSTOM CSS (Neon/Hackathon Theme) ---
st.markdown("""
<style>
    .reportview-container {
        background: #0E1117;
    }
    .big-font {
        font-size:5rem !important;
        color: #00fa9a;
        font-weight: 900;
        text-shadow: 0 0 20px rgba(0, 250, 154, 0.4);
        margin: 0;
        padding: 0;
    }
    .status-badge {
        padding: 5px 10px;
        border-radius: 15px;
        font-weight: bold;
    }
    .stExpander div[data-testid="stText"] {
        font-family: monospace;
    }
</style>
""", unsafe_allow_html=True)

# --- REDIS CONNECTION ---
@st.cache_resource
def get_redis_client():
    try:
        r: redis.Redis = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'), 
            port=int(os.getenv('REDIS_PORT', 6379)), 
            decode_responses=True
        )
        r.ping()
        return r
    except:
        return None

cache = get_redis_client()

# --- DATA FETCHING ---
def fetch_data():
    if not cache:
        return 0.0, []
        
    raw_total = cache.get("total_dollars_saved") 
    total_saved = float(str(raw_total)) if raw_total else 0.0 # type: ignore

    keys: list = cache.keys("audit_trail:*") # type: ignore
    incidents = []
    
    for key in keys: # type: ignore
        incident_id = key.split(":")[1]
        logs_raw: list = cache.lrange(key, 0, -1) # type: ignore
        
        logs_parsed = []
        for x in logs_raw: # type: ignore
            try:
                logs_parsed.append(json.loads(x))
            except (json.JSONDecodeError, TypeError):
                pass
                
        if not logs_parsed:
            continue
            
        # Sort oldest first
        logs_parsed.sort(key=lambda x: x.get("timestamp", 0))
        
        status = "OPEN 🟡"
        resolution_time = None
        start_time = logs_parsed[0].get("timestamp")
        
        for log in logs_parsed:
            action = log.get("action")
            if action == "INCIDENT_VERIFIED":
                status = "RESOLVED ✅"
                if start_time:
                    resolution_time = log.get("timestamp", start_time) - start_time
            elif action in ["ESCALATED_TO_HUMAN", "EXECUTION_FAILED_ESCALATED"]:
                status = "ESCALATED 🔴"
                
        incidents.append({
            "Incident ID": incident_id,
            "Status": status,
            "Logs": logs_parsed,
            "Resolution Time (s)": round(resolution_time, 2) if resolution_time else None,
            "Start Time": datetime.fromtimestamp(start_time).strftime('%H:%M:%S') if start_time else "Unknown",
            "Raw Timestamp": start_time
        })
        
    # Sort incidents from newest to oldest based on start time
    incidents_sorted = sorted(incidents, key=lambda x: x["Raw Timestamp"] if x["Raw Timestamp"] else 0, reverse=True)
    return total_saved, incidents_sorted

# --- UI RENDER ---

# Sidebar Controls
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/8639/8639082.png", width=100)
    st.title("Admin Controls")
    auto_refresh = st.checkbox("🔄 Auto-Refresh Dashboard", value=True)
    st.divider()
    st.markdown("**Agents Online:**")
    st.success("🤖 Diagnostic Agent")
    st.success("🧠 Orchestrator")
    st.success("🦾 Execution Agent")
    st.success("🛡️ SLA Monitor")
    st.success("💰 Verifier Agent")

# Main Dashboard Header
col1, col2 = st.columns([4, 1])
with col1:
    st.title("🚀 Autonomic SRE Command Center")
    st.markdown("*Multi-Agent Collaborative Auto-Remediation Architecture*")
with col2:
    if st.button("🔄 Force Data Sync", use_container_width=True):
        st.rerun()

if cache is None:
    st.error("🚨 CRITICAL: Cannot connect to Redis backend. Please ensure Docker Compose is running (`docker-compose up -d`).")
    st.stop()

total_saved, incidents = fetch_data()

# --- The "Wow" Factor: Money Printer ---
st.markdown("### Total ROI / Downtime Cost Prevented (Live)")
st.markdown(f'<p class="big-font">${total_saved:,.2f}</p>', unsafe_allow_html=True)
st.divider()

# --- Content Layout ---
left_col, right_col = st.columns([1.2, 2])

df = pd.DataFrame(incidents)

with left_col:
    st.subheader("📊 Fleet Health Analytics")
    if not df.empty:
        status_counts = df["Status"].value_counts().reset_index()
        status_counts.columns = ["Status", "Count"]
        
        # Color mapping for pie chart
        color_map = {
            "RESOLVED ✅": "#00fa9a", 
            "ESCALATED 🔴": "#ff4b4b", 
            "OPEN 🟡": "#ffd166"
        }
        
        fig = px.pie(status_counts, values="Count", names="Status", hole=0.5, 
                     color="Status", color_discrete_map=color_map)
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", 
            plot_bgcolor="rgba(0,0,0,0)", 
            margin=dict(t=20, b=20, l=20, r=20),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Quick System Metrics
        resolved_df = df[df["Status"] == "RESOLVED ✅"]
        avg_time = resolved_df["Resolution Time (s)"].mean() if not resolved_df.empty else 0
        
        metric_col1, metric_col2 = st.columns(2)
        with metric_col1:
            st.metric("Avg. Resolution Time", f"{avg_time:.1f}s", delta="-15m (vs Human)" if avg_time > 0 else None)
        with metric_col2:
            st.metric("Total Automated Incidents", len(df))
    else:
        st.info("System is healthy. No incidents detected yet. Run the chaos/diagnostic script to trigger an event.")

with right_col:
    st.subheader("📡 Live Multi-Agent Audit Feed")
    st.markdown("Transparent, auditable log of AI thoughts and actions.")
    
    if not df.empty:
        # Loop through incidents
        for idx, row in df.iterrows():
            # Determine card border color based on status
            border_color = "#00fa9a" if "RESOLVED" in row["Status"] else "#ff4b4b" if "ESCALATED" in row["Status"] else "#ffd166"
            
            with st.expander(f"Incident: {row['Incident ID']} | {row['Status']} | 🕒 {row['Start Time']}", expanded=(idx == 0)):
                for log in row["Logs"]:
                    agent = log.get('agent', 'System')
                    action = log.get('action', 'UNKNOWN')
                    ts = datetime.fromtimestamp(log.get('timestamp', time.time())).strftime('%H:%M:%S')
                    
                    # Custom colors for each agent
                    agent_colors = {
                        "Orchestrator": "#d100d1", # Magenta
                        "Diagnostic Agent": "#00d1d1", # Cyan
                        "Execution": "#ffa500", # Orange
                        "SLA Monitor": "#ff0000", # Red
                        "Verifier": "#00ff00" # Green
                    }
                    color = agent_colors.get(agent, "#ffffff")
                    
                    st.markdown(f"**[{ts}]** 🤖 <span style='color:{color}'>**{agent}**</span> ⚡ `{action}`", unsafe_allow_html=True)
                    
                    # Show payload if it exists
                    payload = log.get("data", None)
                    if not payload and "reason" in log:
                        payload = {"reason": log.get("reason")}
                        
                    if payload:
                        st.json(payload, expanded=False)
    else:
        st.write("Listening to Kafka and Redis event buses...")

# Auto-refresh logic (Runs gracefully at the end of the script)
if auto_refresh:
    time.sleep(2)
    st.rerun()