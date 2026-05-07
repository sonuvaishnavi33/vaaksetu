# VaakSetu — वाक्सेतु

## AI-Powered Multilingual Government Helpline Understanding System

> **“Understanding Before Response”**

VaakSetu is an AI-assisted multilingual voice-to-voice communication system designed for government helplines such as Karnataka’s **1092 citizen support line**.

Unlike traditional chatbots or IVR systems, VaakSetu focuses on one critical principle:

# Correct Understanding Before Action

The system listens to citizens speaking naturally in Kannada, Hindi, English, or mixed dialects, understands emotional and cultural context, verifies its interpretation through a confirmation loop, and safely escalates to human agents whenever confidence is low.

---

# 🚨 Problem Statement

Government helplines often face challenges such as:

* Multilingual callers
* Regional dialects and colloquial speech
* Emotionally distressed citizens
* Miscommunication between citizens and agents
* Unsafe assumptions by automated systems

In emergency or sensitive situations, misunderstanding a citizen can lead to:

* delayed help
* incorrect responses
* reduced trust
* unsafe outcomes

VaakSetu addresses this by ensuring that AI confirms understanding before responding.

---

# 💡 Core Innovation

Traditional systems:

```text id="s6pmtg"
Speech → Response
```

VaakSetu:

```text id="h8bznn"
Speech
↓
Understanding
↓
Confidence Analysis
↓
Confirmation Loop
↓
Response / Escalation
```

If the system is uncertain, it does NOT guess.

It:

* asks clarification questions
* reduces automation
* escalates gracefully to a human operator

---

# 🌟 Key Features

## ✅ Multilingual Voice Understanding

Supports:

* Kannada
* Hindi
* English
* mixed-language conversations

Handles:

* dialect variations
* colloquial speech
* noisy audio
* emotional speech patterns

Powered by:

* Faster Whisper

---

## ✅ Understanding-First AI

The AI extracts:

* issue type
* urgency
* emotional context
* confidence score
* misunderstanding risk
* caller intent

Powered by:

* AWS Bedrock / GPT

---

## ✅ Emotion & Sentiment Detection

Detects:

* fear
* panic
* anger
* sadness
* confusion
* urgency

The AI adapts response style dynamically:

* calming tone
* slower speech
* escalation triggers
* simplified clarification

---

## ✅ Confirmation Loop (Core Feature)

Before taking action, the AI verifies understanding.

Example:

Citizen:

```text id="w0qgzs"
“My phone was stolen... I’m scared...”
```

VaakSetu:

```text id="5h8c9r"
“I understand that your phone may have been stolen and you seem distressed. Is that correct?”
```

Only after confirmation does the system proceed.

---

## ✅ Smart Human Escalation

The system escalates automatically if:

* confidence is low
* distress is high
* repeated misunderstanding occurs
* emergency severity increases

Human agents receive:

* transcript
* emotion indicators
* urgency level
* AI summary
* suggested response
* misunderstanding risk score

---

## ✅ Human-in-the-Loop Design

Agents can:

* review AI understanding
* edit responses
* correct interpretations
* validate emotional context

Corrections become future learning signals.

---

# 🏗️ System Architecture

```text id="f1rq1d"
Citizen Voice
      ↓
Faster Whisper (ASR)
      ↓
Language Detection
      ↓
Emotion Detection
      ↓
Understanding Engine
      ↓
Confidence & Risk Analysis
      ↓
Confirmation Loop
      ↓
Response OR Human Escalation
      ↓
Agent Dashboard
```

---

# 🧠 AI Pipeline

## 1. Speech Recognition

* Faster Whisper
* Real-time multilingual transcription
* Confidence scoring

## 2. Emotion Detection

* Fear
* Panic
* Confusion
* Urgency
* Anger

## 3. Understanding Engine

* Intent extraction
* Context reasoning
* Ambiguity detection
* Clarification generation

## 4. Confirmation Engine

* Understanding verification
* Retry handling
* Confidence tracking

## 5. Escalation Engine

* Safe human handover
* Agent notification
* Emergency prioritization

---

# 🛠️ Tech Stack

| Component               | Technology        |
| ----------------------- | ----------------- |
| Speech Recognition      | Faster Whisper    |
| AI Understanding        | AWS Bedrock / GPT |
| Emotion Detection       | SenseVoice / GPT  |
| Frontend                | Streamlit         |
| Backend                 | FastAPI           |
| Database                | SQLite            |
| Voice Output            | pyttsx3           |
| Real-Time Communication | WebSockets        |

---

# 📂 Project Structure

```text id="z4r76n"
vaaksetu/
├── backend/
│   ├── api/
│   ├── core/
│   ├── websocket/
│   ├── services/
│   └── models/
│
├── ai_pipeline/
│   ├── asr/
│   ├── emotion/
│   ├── understanding/
│   ├── confirmation/
│   └── escalation/
│
├── frontend/
│   └── app.py
│
├── requirements.txt
├── .env.example
└── README.md
```

---

# ⚙️ Installation & Setup

## 1. Clone Repository

```bash id="gakjlwm"
git clone <repository-url>
cd vaaksetu
```

---

## 2. Create Virtual Environment

```bash id="jlwm1x"
python -m venv venv
```

### Windows

```bash id="z14iy0"
venv\Scripts\activate
```

### Linux / Mac

```bash id="gt4gkl"
source venv/bin/activate
```

---

## 3. Install Dependencies

```bash id="o9s1an"
pip install -r requirements.txt
```

---

## 4. Configure Environment Variables

Create `.env` using `.env.example`

Example:

```env
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=ap-south-1

BEDROCK_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0

OPENAI_API_KEY=your_key
```

---

## 5. Start Backend

```bash id="buj49o"
uvicorn backend.main:app --reload --port 8000
```

---

## 6. Start Frontend

```bash id="sxzg3c"
streamlit run frontend/app.py
```

---

## 7. Access Application

Frontend:

```text id="sulvbg"
http://localhost:8501
```

Backend API Docs:

```text id="snhp2g"
http://localhost:8000/docs
```

---

# 🎬 Demo Scenario

## Scenario: Distressed Theft Victim

Citizen:

```text id="44qpkm"
“Mera phone chori ho gaya... I’m alone... bahut darr lag raha hai...”
```

System detects:

* Mixed Hindi + English
* Fear and urgency
* Possible theft case

VaakSetu:

```text id="xt1m7u"
“I understand your phone may have been stolen and you seem frightened. Is that correct?”
```

Citizen:

```text id="s45yyj"
“Yes”
```

Action:

* AI confirms understanding
* Agent receives escalation alert
* Emotion timeline shown on dashboard
* Suggested response generated

---

# 🔐 Security & Safety

* Environment variables stored in `.env`
* No hardcoded secrets
* `.env` excluded using `.gitignore`
* Confidence-aware responses
* No-guessing policy
* Human override support

---

# 🚀 Future Improvements

* Regional dialect fine-tuning
* Additional Indian languages
* Real-time translation layer
* Emergency prioritization queues
* Voice cloning for natural responses
* Analytics dashboard
* Government cloud deployment
* Offline edge deployment

---

# 🏛️ Government Deployment Vision

VaakSetu is designed to scale beyond a hackathon prototype.

Possible deployment roadmap:

## Phase 1

Local prototype with simulated calls

## Phase 2

District-level pilot deployment

## Phase 3

State-wide multilingual integration

## Phase 4

Pan-India multilingual citizen support platform

---

# 🏆 Why VaakSetu Matters

Most AI systems prioritize speed.

VaakSetu prioritizes:

* trust
* empathy
* safety
* verified understanding

Because in citizen services:

# Wrong understanding is more dangerous than slow response.

---

---

# 📜 License

This project is intended for educational, research, and hackathon purposes.
