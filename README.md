# Telephone Translator Remote MCP Server

A minimal, secure, and fast Python Remote Model Context Protocol (MCP) server designed for deployment on Railway and connection to Perplexity as a custom Remote connector.

This server exposes two utility tools for LLM use:
1. `telephone_translate`: mangles text by translating it through multiple random languages and back to target language (default `en`), while optionally preserving double-quoted text.
2. `format_text`: formats and tidies paragraphs, straightens curly quotes, removes duplicate spaces, and corrects common spelling mistakes.

---

## Technical Stack & Configuration

- **Core**: Python + FastAPI
- **Dependencies**: HTTPX (for async translations), Uvicorn (web server)
- **Deployment**: Configured for Railway with `railway.json` using Nixpacks (no Dockerfile required)
- **Authentication**: Standard `Authorization: Bearer <key>` header protection

---

## Local Setup & Development

### 1. Prerequisite
Ensure Python 3.9+ is installed.

### 2. Set Up the Environment
Create a virtual environment and install the dependencies:
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Set the Secret Key
Before starting the server, you must set the `MCP_API_KEY` environment variable. The server will fail to start (fail-fast) if this variable is missing.

**On Windows (PowerShell):**
```powershell
$env:MCP_API_KEY="YOUR_SECRET_KEY"
```

**On Windows (CMD):**
```cmd
set MCP_API_KEY=YOUR_SECRET_KEY
```

**On macOS/Linux:**
```bash
export MCP_API_KEY="YOUR_SECRET_KEY"
```

### 4. Run the Server
Start the local server using Uvicorn:
```bash
python -m uvicorn server:app --reload --host 127.0.0.1 --port 8000
```

---

## Local Verification with cURL

Open another terminal and run the following curl commands to verify behavior.

### 1. Health Check (Unprotected GET)
```bash
curl -X GET http://127.0.0.1:8000/
```
**Response:**
```json
{"status":"healthy","service":"Telephone Translator Remote MCP Server","version":"1.0.0"}
```

### 2. Test Missing Authentication (Should return 401)
```bash
curl -i -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```
**Response:** HTTP 401 Unauthorized (`{"detail":"Missing Authorization header"}`)

### 3. Test Invalid Token (Should return 401)
```bash
curl -i -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer WRONG_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```
**Response:** HTTP 401 Unauthorized (`{"detail":"Invalid API key"}`)

### 4. List Available Tools (tools/list)
```bash
curl -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer YOUR_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```

### 5. Call `telephone_translate`
```bash
curl -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer YOUR_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "telephone_translate",
      "arguments": {
        "text": "Hello \"world\", this is a \"special key\" that we want to preserve while mangling the rest.",
        "rounds": 5,
        "return_language": "en",
        "preserve_quotes": true
      }
    },
    "id": 2
  }'
```

### 6. Call `format_text`
```bash
curl -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer YOUR_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "format_text",
      "arguments": {
        "text": "Teh wierd  curly  quotes like “this”  will be fixed  untill we recieve it.",
        "remove_double_spaces": true,
        "straighten_quotes": true,
        "fix_spelling": true,
        "indent_paragraphs": true
      }
    },
    "id": 3
  }'
```

---

## Step-by-Step GitHub & Railway Deployment

Follow these exact steps to deploy your server to the cloud.

### Step 1: Create a GitHub Repository
1. Log in to [GitHub](https://github.com).
2. Click **New** (or go to `https://github.com/new`) to create a new repository.
3. Name it `telephone-mcp-remote`, set the visibility to **Private** (recommended since it runs a private MCP server), and click **Create repository**.
4. In your local terminal, initialize git inside your project folder, commit your files, and push them:
   ```bash
   git init
   git add .
   git commit -m "Initial commit of remote MCP server"
   git branch -M main
   git remote add origin https://github.com/YOUR_GITHUB_USERNAME/telephone-mcp-remote.git
   git push -u origin main
   ```

### Step 2: Deploy on Railway
1. Go to [Railway](https://railway.app) and log in.
2. Click **New Project** in the upper right.
3. Choose **Deploy from GitHub repo**.
4. Select your `telephone-mcp-remote` repository.
5. Railway will automatically set up the builder (Nixpacks) and build the application according to the rules in `railway.json`.

### Step 3: Set `MCP_API_KEY` Environment Variable
1. Once the service is created in Railway, click on the service block.
2. Go to the **Variables** tab.
3. Click **Add Variable** (or **New Variable**).
4. Enter `MCP_API_KEY` as the variable name.
5. Enter your secure API key (e.g., `YOUR_SECRET_KEY`) as the value.
6. Click **Add** to save. Railway will automatically redeploy the application with this environment variable configured.

### Step 4: Expose Public Domain
1. In the service dashboard, go to the **Settings** tab.
2. Under the **Public Networking** / **Domains** section, click **Generate Domain** (or set up a custom domain).
3. Railway will generate a public URL such as `https://telephone-mcp-remote-production.up.railway.app`. Keep this URL handy.

---

## Connecting to Perplexity

To use this server as a custom Remote connector inside Perplexity:

1. Open **Perplexity AI** and navigate to your **Account Settings** / **Custom Connectors** / **Remote MCP**.
2. Click **Add Custom Server** (or similar button).
3. Fill out the configuration with these values:
   - **Name**: `Telephone Translator`
   - **MCP Server URL**: `https://YOUR-APP.up.railway.app/mcp` (replace `YOUR-APP` with your actual Railway generated domain)
   - **Authentication**: `API Key`
   - **API Key Value**: Enter the exact secret key you set in your `MCP_API_KEY` variable on Railway.
   - **Transport**: `Streamable HTTP`
4. Click **Connect** or **Save**. Perplexity will ping your server's `/mcp` with `tools/list` to fetch the tools list and complete the connection successfully.
