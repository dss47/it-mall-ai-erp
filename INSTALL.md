# 🚀 IT Mall – Installation & Deployment Guide

This guide provides step-by-step instructions to set up, configure, and run the complete **IT Mall AI & ERP Suite** on a fresh Linux machine (Ubuntu 22.04 / 24.04 recommended).

---

## 📋 Prerequisites

Ensure you have the following installed on your host system:
- **Docker & Docker Compose**
- **Python 3.10+** & `pip`
- **PostgreSQL** (or run via Docker)
- **Odoo 18.0**
- API Keys:
  - **Groq API Key** (for Whisper STT & fast inference)
  - **Google Gemini API Key** (optional / fallback LLM)
  - **Meta WhatsApp Cloud API Token** & Phone Number ID

---

## 🛠️ Step 1: Clone & Environment Setup

```bash
# Clone the repository
git clone https://github.com/your-username/it-mall-ai-erp.git
cd it-mall-ai-erp

# Create environment configuration for Voice Agent
cp voice-agent/db.env.example voice-agent/db.env
```

Edit `voice-agent/db.env` with your credentials:
```ini
# Meta WhatsApp Cloud API
WHATSAPP_TOKEN=EAAU...your_permanent_system_user_token
WHATSAPP_PHONE_ID=1276761165518057

# LLM & Voice Services
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...

# Odoo Connection (XML-RPC & DB)
ODOO_URL=http://localhost:8069
ODOO_DB=odoo
ODOO_USER=admin
ODOO_PASSWORD=your_odoo_password
```

---

## 🎙️ Step 2: Set Up Python Voice Agent & Dependencies

```bash
cd voice-agent

# Create and activate Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install required Python packages
pip install --upgrade pip
pip install fastapi uvicorn requests psycopg2-binary onnxruntime numpy groq google-generativeai

# Download local Piper neural TTS model (French Siwis voice)
mkdir -p piper && cd piper
wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz
tar -xvf piper_amd64.tar.gz
wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json
cd ..
```

---

## 📞 Step 3: Telephony & PBX (Asterisk / FreePBX)

You can launch FreePBX and restore the pre-configured telephony environment in two simple commands:

```bash
# 1. Start FreePBX container
docker run -d --name freepbx --net=host -v /etc/asterisk:/etc/asterisk mleem97/lnxr-freepbx:17

# 2. Restore complete pre-configured Asterisk & FreePBX settings
docker exec -i freepbx tar -xzf - -C / < telephony/freepbx_config.tar.gz
docker exec freepbx fwconsole reload
```

*Dialing extension `*99` from any SIP client (Zoiper, MicroSIP) is already mapped to route calls to the Python AudioSocket server on port `:8300`.*

---

## 🏢 Step 4: Install Odoo 18 Module

1. Copy the `it_mall_branding` addon to your Odoo addons directory:
   ```bash
   sudo cp -r odoo-addons/it_mall_branding /opt/odoo-addons/
   ```
2. Restart Odoo server:
   ```bash
   sudo systemctl restart odoo
   ```
3. Log into Odoo as Admin:
   - Go to **Apps** -> Click **Update Apps List**.
   - Search for **IT Mall Branding & Operations**.
   - Click **Install / Upgrade**.

---

## ⚡ Step 5: Import n8n Workflow

1. Start n8n container:
   ```bash
   docker run -d --name n8n -p 5678:5678 -v /opt/n8n/data:/home/node/.n8n n8nio/n8n:latest
   ```
2. Open `http://localhost:5678` in your browser.
3. Click **Workflows** -> **Import from File**.
4. Select `n8n-workflows/it_mall_post_call.json`.
5. Toggle the workflow status to **Active**.

---

## 🚀 Step 6: Start the Microservices

In separate terminals (or configure as systemd services):

1. **Start the AudioSocket Voice Server**:
   ```bash
   cd voice-agent
   source venv/bin/activate
   python3 -m agent.server
   ```
   *(Listens on TCP port `8300` for real-time Asterisk bidirectional audio streaming)*

2. **Start the PDF & WhatsApp Microservice**:
   ```bash
   cd voice-agent
   source venv/bin/activate
   uvicorn agent.pdf_service:app --host 0.0.0.0 --port 8301
   ```

---

## 🧪 Step 7: End-to-End Live Verification

1. **Place a Call**: Dial extension `*99` from your SIP softphone (e.g. Zoiper).
2. **Interact with AI**: Inquire about catalog products (e.g., *"Bonjour, avez-vous des bornes WiFi UniFi ?"*).
3. **Verify Automation**:
   - The AI checks PostgreSQL real-time inventory and announces stock & prices dynamically.
   - Upon hangup, the voice session sends the payload to n8n (`http://127.0.0.1:5678/webhook/hotline`).
   - n8n creates a CRM Lead and Sales Order in Odoo.
   - Microservice `:8301` generates the official QWeb PDF quote and delivers it to the caller's WhatsApp with a thank-you note.

---

## 🪟 Windows Deployment Guide (via WSL2 & Docker Desktop)

To run the complete **IT Mall Suite on Windows 10 / 11**, use **WSL2 (Windows Subsystem for Linux)** to ensure native Linux performance for Asterisk VoIP networking and Python audio processing.

### 1. Prerequisites on Windows
1. **Enable WSL2**: Open PowerShell as Administrator and run:
   ```powershell
   wsl --install -d Ubuntu-22.04
   ```
2. **Install Docker Desktop**:
   - Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
   - In Docker Desktop Settings: Go to **General** -> Enable **Use the WSL 2 based engine**.
   - Go to **Resources** -> **WSL Integration** -> Enable integration with your `Ubuntu-22.04` distro.

### 2. Quick Setup inside WSL2
Open your **Ubuntu WSL terminal** and execute the exact same Linux steps:
```bash
# Inside WSL Ubuntu:
git clone https://github.com/your-username/it-mall-ai-erp.git
cd it-mall-ai-erp

# Follow Steps 1 to 7 from the Linux section above!
```

### 3. Connecting Windows Softphones (Zoiper / MicroSIP)
- You can install **MicroSIP** or **Zoiper** directly on Windows.
- Connect your SIP account to Domain / Server: `127.0.0.1` (or `localhost`).
- Dial `*99` directly from Windows to test the voice agent running inside WSL2/Docker!
