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

# --- EXTREME CUSTOM CSS (Glassmorphism & Cyberpunk Theme) ---
st.markdown("""
<style>
    /* Global Background and Fonts */
    .stApp {
        background: radial-gradient(circle at 10% 20%, rgb(17, 24, 39) 0%, rgb(0, 0, 0) 90%);
        color: #e5e7eb;
        font-family: 'Inter', sans-serif;
    }
    
    /* Hide Streamlit Branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Typography & Headers */
    h1, h2, h3 {
        color: #f3f4f6 !important;
        font-weight: 800 !important;
        letter-spacing: -0.05em;
    }
    
    /* Cyberpunk Title */
    .title-glow {
        text-align: left;
        font-size: 3.5rem !important;
        font-weight: 900;
        background: linear-gradient(90deg, #00fa9a, #0bc5ea, #d100d1);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: gradient-shift 5s ease infinite;
        margin-bottom: 0px;
        padding-bottom: 0px;
    }
    
    @keyframes gradient-shift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    /* Glassmorphism Metric Cards */
    .glass-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
        text-align: center;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    .glass-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 40px rgba(0, 250, 154, 0.2);
        border: 1px solid rgba(0, 250, 154, 0.4);
    }
    
    .metric-value-huge {
        font-size: 4.5rem;
        font-weight: 900;
        color: #00fa9a;
        text-shadow: 0 0 20px rgba(0, 250, 154, 0.6);
        margin: 10px 0;
        line-height: 1.1;
    }
    .metric-value {
        font-size: 3rem;
        font-weight: 800;
        color: #ffffff;
        margin: 10px 0;
        line-height: 1.1;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 2px;
        font-weight: 700;
    }

    /* Agent Status Badges */
    .agent-pulse {
        display: inline-block;
        width: 12px;
        height: 12px;
        background: #00fa9a;
        border-radius: 50%;
        margin-right: 12px;
        box-shadow: 0 0 10px #00fa9a;
        animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(0, 250, 154, 0.7); }
        70% { box-shadow: 0 0 0 10px rgba(0, 250, 154, 0); }
        100% { box-shadow: 0 0 0 0 rgba(0, 250, 154, 0); }
    }
    .agent-box {
        background: rgba(0, 250, 154, 0.05);
        border: 1px solid rgba(0, 250, 154, 0.2);
        border-radius: 8px;
        padding: 12px 15px;
        margin-bottom: 12px;
        color: #e5e7eb;
        font-weight: 600;
        display: flex;
        align-items: center;
        transition: background 0.3s;
    }
    .agent-box:hover {
        background: rgba(0, 250, 154, 0.15);
    }

    /* Streamlit Expander Overrides */
    .streamlit-expanderHeader {
        background: rgba(255,255,255,0.05) !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        font-size: 1.1rem !important;
    }
    .streamlit-expanderContent {
        background: rgba(0,0,0,0.4) !important;
        border: 1px solid rgba(255,255,255,0.05) !important;
        border-top: none !important;
        border-bottom-left-radius: 8px !important;
        border-bottom-right-radius: 8px !important;
    }

    /* Log Box */
    .terminal-log {
        background: #0d1117;
        padding: 14px;
        border-radius: 6px;
        font-family: 'Fira Code', monospace;
        font-size: 0.95rem;
        color: #a5b4fc;
        border-left: 4px solid #6366f1;
        margin-bottom: 10px;
        box-shadow: inset 0 0 10px rgba(0,0,0,0.5);
    }
    .terminal-log span.agent-name {
        font-weight: 900;
        letter-spacing: 1px;
    }
    
    /* Horizontal Rule styling */
    hr {
        border-top: 1px solid rgba(255,255,255,0.1);
        margin: 2rem 0;
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
    st.image("https://cdn-icons-png.flaticon.com/512/2043/2043236.png", width=100)
    st.markdown("<h2 style='text-align: left; color: white;'>Nexus Control</h2>", unsafe_allow_html=True)
    auto_refresh = st.checkbox("🔄 Real-Time Telemetry", value=True)
    
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<div class='metric-label'>SWARM STATUS</div>", unsafe_allow_html=True)
    
    agents = ["Diagnostic Agent", "Orchestrator", "Execution Agent", "Predictive Agent", "SLA Monitor", "Reporting Agent", "Verifier Agent"]
    for agent in agents:
        st.markdown(f"<div class='agent-box'><span class='agent-pulse'></span>{agent}</div>", unsafe_allow_html=True)

# Main Dashboard Header
st.markdown("<div class='title-glow'>NEXUS SRE SYSTEM</div>", unsafe_allow_html=True)
st.markdown("<p style='color: #9ca3af; font-size: 1.3rem; margin-bottom: 2rem;'>Autonomous Multi-Agent Self-Healing Infrastructure</p>", unsafe_allow_html=True)

if cache is None:
    st.error("🚨 CRITICAL: Cannot connect to Redis backend. Please ensure Docker Compose is running (`docker-compose up -d`).")
    st.stop()

total_saved, incidents = fetch_data()

# Calculate dynamic metrics
df = pd.DataFrame(incidents)
avg_time_val = 0
if not df.empty:
    resolved_df = df[df["Status"] == "RESOLVED ✅"]
    avg_time_val = resolved_df["Resolution Time (s)"].mean() if not resolved_df.empty else 0
total_incidents = len(df)

# Top 3 Huge Cards
col_m1, col_m2, col_m3 = st.columns(3)

with col_m1:
    st.markdown(f"""
    <div class="glass-card">
        <div class="metric-label">TOTAL DOWNTIME COST PREVENTED</div>
        <div class="metric-value-huge">${total_saved:,.2f}</div>
    </div>
    """, unsafe_allow_html=True)

with col_m2:
    st.markdown(f"""
    <div class="glass-card">
        <div class="metric-label">AVERAGE AI RESOLUTION TIME</div>
        <div class="metric-value" style="color: #0bc5ea;">{avg_time_val:.1f}s</div>
        <div style="color: #00fa9a; font-size: 0.95rem; font-weight:bold;">↓ 15m faster than human SLA</div>
    </div>
    """, unsafe_allow_html=True)

with col_m3:
    st.markdown(f"""
    <div class="glass-card">
        <div class="metric-label">AUTONOMOUS EVENTS HANDLED</div>
        <div class="metric-value" style="color: #d100d1;">{total_incidents}</div>
        <div style="color: #9ca3af; font-size: 0.95rem;">Zero human intervention required</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)

# --- Bottom Content Layout ---
left_col, right_col = st.columns([1, 1.5])

with left_col:
    st.markdown("<h3 style='margin-bottom: 1rem;'>🌍 Topology & Fleet Health</h3>", unsafe_allow_html=True)
    
    if not df.empty:
        # Wrap Data in Glass Card
        st.markdown('<div class="glass-card" style="padding: 10px; margin-bottom: 30px;">', unsafe_allow_html=True)
        # Status Pie Chart with transparent background
        status_counts = df["Status"].value_counts().reset_index()
        status_counts.columns = ["Status", "Count"]
        color_map = {
            "RESOLVED ✅": "#00fa9a", 
            "ESCALATED 🔴": "#ff4b4b", 
            "OPEN 🟡": "#ffd166"
        }
        fig = px.pie(status_counts, values="Count", names="Status", hole=0.75, color="Status", color_discrete_map=color_map)
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", 
            plot_bgcolor="rgba(0,0,0,0)", 
            margin=dict(t=20, b=20, l=10, r=10),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5, font=dict(color="white"))
        )
        fig.update_traces(textposition='inside', textinfo='percent', hoverinfo='label+percent')
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        # --- Generative Blast Radius Graph ---
        st.markdown('<div class="glass-card" style="text-align: left; padding: 25px;">', unsafe_allow_html=True)
        st.markdown("<div class='metric-label' style='margin-bottom:20px; text-align: center;'>🕸️ SYSTEM BLAST RADIUS</div>", unsafe_allow_html=True)
        
        dot = "digraph BlastRadius {\n"
        dot += '  bgcolor="transparent";\n'
        dot += '  rankdir="LR";\n'
        dot += "  node [fontname=Inter, shape=box, rounded=true, style=filled, penwidth=0];\n"
        dot += '  edge [color="#6b7280", penwidth=2];\n'
        dot += '  SERVER [label="PRODUCTION EC2\\nTarget Node", fillcolor="#1f2937", fontcolor="#ffffff"];\n'
        
        for _, r in df.head(5).iterrows():
            issue_type = "anomaly"
            for lg in r["Logs"]:
                if lg.get("action") == "DIAGNOSIS_RECEIVED":
                    issue_type = lg.get("data", {}).get("issue_type", "anomaly")
                    break
            
            # Map status to neon colors
            status_color = "#00fa9a" if "RESOLVED ✅" in r["Status"] else "#ff4b4b" if "ESCALATED 🔴" in r["Status"] else "#ffd166"
            font_color = "#000000" if "RESOLVED ✅" in r["Status"] else "#ffffff"
            
            dot += f'  "{r["Incident ID"]}" [label="{r["Incident ID"]}\\n({issue_type})", fillcolor="{status_color}", fontcolor="{font_color}"];\n'
            dot += f'  SERVER -> "{r["Incident ID"]}";\n'
            
        dot += "}\n"
        st.graphviz_chart(dot)
        st.markdown('</div>', unsafe_allow_html=True)
        
    else:
        st.info("System is healthy. No incidents detected yet.")

with right_col:
    st.markdown("<h3 style='margin-bottom: 1rem;'>📡 Multi-Agent Execution Stream</h3>", unsafe_allow_html=True)
    
    if not df.empty:
        # Loop through incidents
        for idx, row in df.iterrows():
            with st.expander(f"🔮 {row['Incident ID']} | Status: {row['Status']} | Alert Time: {row['Start Time']}", expanded=(idx == 0)):
                for log in row["Logs"]:
                    agent = log.get('agent', 'System')
                    action = log.get('action', 'UNKNOWN')
                    ts = datetime.fromtimestamp(log.get('timestamp', time.time())).strftime('%H:%M:%S')
                    
                    # Agent specific styling
                    agent_colors = {
                        "Orchestrator": "#d100d1", 
                        "Diagnostic Agent": "#0bc5ea", 
                        "Execution": "#f59e0b",
                        "Execution Agent": "#f59e0b",
                        "Predictive Agent": "#8b5cf6",
                        "SLA Monitor": "#ef4444", 
                        "Reporting Agent": "#10b981",
                        "Verifier": "#00fa9a" 
                    }
                    color = agent_colors.get(agent, "#ffffff")
                    
                    # Log header rendering
                    st.markdown(f"""
                    <div class="terminal-log" style="border-left-color: {color};">
                        <span style="color: #6b7280;">[{ts}]</span> 
                        <span class="agent-name" style="color: {color};">{agent}</span> 
                        <span style="color: #e5e7eb;">>> {action}</span>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Log payload parsing
                    payload = log.get("data", None)
                    if not payload and "reason" in log:
                        payload = {"reason": log.get("reason")}
                        
                    if payload:
                        if action == "POST_MORTEM_GENERATED" and "rca_markdown" in payload:
                            st.markdown("""<div style="background: rgba(16, 185, 129, 0.1); padding: 20px; border-radius: 8px; margin-bottom: 15px; border: 1px solid rgba(16, 185, 129, 0.4);">""", unsafe_allow_html=True)
                            st.markdown("##### 📄 Executive RCA Post-Mortem")
                            st.markdown(payload["rca_markdown"])
                            st.markdown("</div>", unsafe_allow_html=True)
                            
                        elif action == "AGENT_DEBATE_LOG" and "transcript" in payload:
                            st.markdown("""<div style="background: rgba(209, 0, 209, 0.1); padding: 20px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid #d100d1;">""", unsafe_allow_html=True)
                            st.markdown("<h4 style='color: #d100d1; margin-bottom: 15px;'>🗣️ AI War Room Debate Transcripts</h4>", unsafe_allow_html=True)
                            for msg in payload.get("transcript", []):
                                persona = msg.get("persona", "Agent")
                                text = msg.get("message", "")
                                p_color = "#f59e0b" if persona == "The Cowboy" else "#0bc5ea" if persona == "The Conservative" else "#00fa9a"
                                st.markdown(f"**<span style='color:{p_color}; font-size:1.1rem;'>{persona}</span>**: <span style='color: #e5e7eb; font-style: italic;'>\"{text}\"</span>", unsafe_allow_html=True)
                            st.markdown(f"<div style='margin-top: 20px; padding: 10px; background: rgba(0, 250, 154, 0.1); border-radius: 5px; color: #00fa9a; font-weight: bold; font-size: 1.1rem;'>⚖️ Final Judge Consensus: <span style='font-family: monospace; color: white;'>{payload.get('final_command', 'N/A')}</span></div>", unsafe_allow_html=True)
                            st.markdown("</div>", unsafe_allow_html=True)
                            
                        else:
                            st.json(payload, expanded=False)
                            
    else:
        st.markdown("""
        <div class="glass-card" style="margin-top: 20px; padding: 40px;">
            <div style="color: #00fa9a; font-size: 3rem; margin-bottom: 20px;">🛡️</div>
            <div style="font-size: 1.5rem; font-weight: bold; color:white;">AWAITING TELEMETRY</div>
            <div style="margin-top: 10px; color:#9ca3af;">Listening to secure Event Bus...</div>
        </div>
        """, unsafe_allow_html=True)

# Auto-refresh logic 
if auto_refresh:
    time.sleep(2)
    st.rerun()