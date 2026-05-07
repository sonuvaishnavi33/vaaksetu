import streamlit as st
import requests
import json
from datetime import datetime
from typing import Optional

st.set_page_config(
    page_title="VaakSetu — Emergency Helpline",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

API_BASE = "http://localhost:8000/api/v1"

# Modern, clean CSS
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
* { font-family: 'Inter', sans-serif; }

html, body, .stApp {
    background-color: #f8f9fa !important;
    color: #1f2937 !important;
}

.main .block-container { padding: 2.5rem 3rem; max-width: 1200px; }

.header-main { 
    font-size: 3rem; 
    font-weight: 700; 
    color: #2563eb;
    margin: 0.5rem 0;
}

.subheader {
    color: #6b7280;
    font-size: 1.1rem;
    margin: 0.5rem 0 2rem 0;
}

.card {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 1.5rem;
    margin: 1rem 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.card-danger {
    border-left: 4px solid #ef4444;
    background: #fef2f2;
}

.card-success {
    border-left: 4px solid #10b981;
    background: #f0fdf4;
}

.metric {
    text-align: center;
    padding: 1.5rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    margin: 0.5rem;
}

.metric-value {
    font-size: 2.5rem;
    font-weight: 700;
    color: #2563eb;
}

.metric-label {
    font-size: 0.9rem;
    color: #6b7280;
    margin-top: 0.5rem;
}

.transcript {
    background: white;
    border-radius: 8px;
    padding: 1rem;
    margin: 0.75rem 0;
    border-left: 4px solid #2563eb;
}

.transcript-ai {
    border-left-color: #10b981;
    background: #f0fdf4;
}

.stButton button {
    background: #2563eb !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.75rem 1.5rem !important;
    font-weight: 600 !important;
}

.stButton button:hover {
    background: #1d4ed8 !important;
}

.warning-box {
    background: #fef3c7;
    border: 1px solid #fcd34d;
    border-radius: 8px;
    padding: 1rem;
    margin: 1rem 0;
}

.success-box {
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 8px;
    padding: 1rem;
    margin: 1rem 0;
}

.danger-box {
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 8px;
    padding: 1rem;
    margin: 1rem 0;
}

.badge {
    display: inline-block;
    padding: 0.35rem 0.75rem;
    border-radius: 999px;
    font-weight: 600;
    font-size: 0.85rem;
    margin-right: 0.5rem;
}

.badge-danger { background: #fee2e2; color: #991b1b; }
.badge-warning { background: #fef3c7; color: #92400e; }
.badge-success { background: #f0fdf4; color: #166534; }
.badge-info { background: #dbeafe; color: #0c4a6e; }

h1, h2, h3 { color: #1f2937 !important; }
</style>
""", unsafe_allow_html=True)

# Initialize state
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "transcript" not in st.session_state:
    st.session_state.transcript = []
if "current_session_data" not in st.session_state:
    st.session_state.current_session_data = {}

# Helper functions
def api_post(endpoint: str, data: dict) -> Optional[dict]:
    try:
        r = requests.post(f"{API_BASE}{endpoint}", json=data, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Backend not running on http://localhost:8000")
        return None
    except Exception as e:
        st.error(f"Error: {e}")
        return None

def api_get(endpoint: str) -> Optional[dict]:
    try:
        r = requests.get(f"{API_BASE}{endpoint}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

# Header
st.markdown('<div class="header-main">🛡️ VaakSetu</div>', unsafe_allow_html=True)
st.markdown('<div class="subheader">वाक्सेतु · AI-Powered Emergency Helpline Assistant</div>', unsafe_allow_html=True)

# Main interface
col_main, col_status = st.columns([3, 1])

with col_main:
    st.markdown("## 📞 Call Session")
    
    # Session control
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶ Start New Session", type="primary", use_container_width=True):
            resp = api_post("/session/start", {})
            if resp and "session_id" in resp:
                st.session_state.session_id = resp["session_id"]
                st.session_state.transcript = []
                st.session_state.current_session_data = {
                    "start_time": datetime.now(),
                    "emotion": "neutral",
                    "urgency": 0.0,
                    "panic": False,
                    "confidence": 0.0,
                    "messages": [],
                }
                st.success(f"✅ Session started: {st.session_state.session_id[:16]}...")
    
    with c2:
        if st.session_state.session_id and st.button("⏹ End Session", use_container_width=True):
            if st.session_state.session_id:
                api_post(f"/session/{st.session_state.session_id}/end", {})
            st.session_state.session_id = None
            st.session_state.transcript = []
            st.info("Session ended.")

    st.markdown("---")

    if not st.session_state.session_id:
        st.warning("👆 Click 'Start New Session' above to begin.")
    else:
        # Message input
        st.markdown("### 💬 Citizen Message")
        user_input = st.text_area(
            "What is the citizen saying?",
            height=100,
            placeholder="Enter the caller's message in any language...",
            label_visibility="collapsed",
        )

        col_btn1, col_btn2, col_btn3 = st.columns(3)
        with col_btn1:
            process_btn = st.button("🔄 Process Message", type="primary", use_container_width=True)
        with col_btn2:
            escalate_btn = st.button("🚨 Emergency Escalate", use_container_width=True)
        with col_btn3:
            save_btn = st.button("💾 Save Session", use_container_width=True)

        if process_btn and user_input.strip():
            with st.spinner("⏳ Processing through AI pipeline..."):
                resp = api_post("/process/text", {
                    "text": user_input,
                    "session_id": st.session_state.session_id,
                    "language": "en",
                })

                if resp:
                    # Update state
                    emotion_data = resp.get("emotion", {})
                    understanding = resp.get("understanding", {})
                    confirmation = resp.get("confirmation", {})

                    st.session_state.current_session_data.update({
                        "emotion": emotion_data.get("primary", "neutral"),
                        "urgency": emotion_data.get("urgency", 0.0),
                        "panic": emotion_data.get("panic", False),
                        "confidence": understanding.get("confidence", 0.0),
                        "intent": understanding.get("intent", ""),
                        "issue_type": understanding.get("issue_type", ""),
                    })

                    # Add to transcript
                    st.session_state.transcript.append({
                        "speaker": "citizen",
                        "text": user_input,
                        "time": datetime.now().strftime("%H:%M:%S"),
                    })

                    if confirmation.get("prompt"):
                        st.session_state.transcript.append({
                            "speaker": "ai",
                            "text": confirmation["prompt"],
                            "time": datetime.now().strftime("%H:%M:%S"),
                        })

                    st.rerun()

        if escalate_btn:
            if st.session_state.session_id:
                resp = api_post("/escalate", {
                    "session_id": st.session_state.session_id,
                    "reason": "citizen_emergency",
                })
                st.markdown('<div class="danger-box"><strong>🚨 Escalated to Human Agent</strong></div>', unsafe_allow_html=True)

        # Transcript display
        if st.session_state.transcript:
            st.markdown("### 📝 Conversation")
            for msg in st.session_state.transcript[-15:]:
                if msg["speaker"] == "citizen":
                    st.markdown(f"""
                    <div class="transcript">
                        <strong>👤 Citizen</strong> <span style="color:#9ca3af; font-size:0.85rem;">{msg['time']}</span><br/>
                        {msg['text']}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="transcript transcript-ai">
                        <strong>🤖 VaakSetu</strong> <span style="color:#9ca3af; font-size:0.85rem;">{msg['time']}</span><br/>
                        {msg['text']}
                    </div>
                    """, unsafe_allow_html=True)

with col_status:
    st.markdown("## 📊 Status")

    data = st.session_state.current_session_data

    # Panic alert
    if data.get("panic"):
        st.markdown("""
        <div class="danger-box">
            <strong>🚨 PANIC DETECTED</strong><br/>
            <small>Immediate human escalation recommended</small>
        </div>
        """, unsafe_allow_html=True)

    # Metrics
    st.markdown(f"""
    <div class="metric">
        <div class="metric-value">{int(data.get('confidence', 0) * 100)}%</div>
        <div class="metric-label">Confidence</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="metric">
        <div class="metric-value">{int(data.get('urgency', 0) * 100)}%</div>
        <div class="metric-label">Urgency</div>
    </div>
    """, unsafe_allow_html=True)

    # Emotion badge
    emotion = data.get("emotion", "neutral")
    emotion_colors = {
        "panic": "danger",
        "fear": "warning",
        "anger": "danger",
        "sadness": "info",
        "confusion": "warning",
        "neutral": "info",
        "calm": "success",
    }
    badge_type = emotion_colors.get(emotion, "info")
    st.markdown(f'<span class="badge badge-{badge_type}">{emotion.upper()}</span>', unsafe_allow_html=True)

    # Intent
    if data.get("intent"):
        st.markdown(f"""
        <div style="background: #f3f4f6; padding: 0.75rem; border-radius: 6px; margin-top: 1rem; font-size: 0.9rem;">
            <strong>Intent:</strong> {data['intent']}<br/>
            <strong>Type:</strong> {data.get('issue_type', 'Unknown')}
        </div>
        """, unsafe_allow_html=True)

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #9ca3af; font-size: 0.85rem;">
    <strong>VaakSetu v1.0</strong> | AI-Powered Government Helpline<br/>
    Backend: <span style="font-family: monospace;">http://localhost:8000/docs</span>
</div>
""", unsafe_allow_html=True)
