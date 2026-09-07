# Local RAG — Setup and Access Guide

For administrators and people using Local RAG from a phone, tablet or computer.

Updated: September 7, 2026. Based on this repository's custom FastAPI + React application, **not Open WebUI**. The separately documented `server-build/` stack has different instructions.

> Most people only need a browser, the server address and their personal API key. They do not install Python, Ollama, a database or AI models on their device.

## Contents

1. [Choose your setup](#1-choose-your-setup)
2. [Connect as a user](#2-connect-as-a-user)
3. [Start an existing Windows host](#3-start-an-existing-windows-host)
4. [Create users and grant document access](#4-create-users-and-grant-document-access)
5. [Private remote access with Tailscale](#5-private-remote-access-with-tailscale)
6. [Same-Wi-Fi access](#6-same-wi-fi-access)
7. [Chat and use documents](#7-chat-and-use-documents)
8. [Connect scripts and API applications](#8-connect-scripts-and-api-applications)
9. [Install a new Windows host](#9-install-a-new-windows-host)
10. [Restart, stop and maintain the host](#10-restart-stop-and-maintain-the-host)
11. [Troubleshooting](#11-troubleshooting)
12. [Acceptance checklist](#12-acceptance-checklist)
13. [Quick reference](#13-quick-reference)

## 1. Choose your setup

| Your situation | What to do |
|---|---|
| Someone already runs the server; you want to chat | Follow section 2. Ask the administrator for access. |
| You administer this project's existing laptop/server | Follow sections 3–4, then choose 5 or 6. |
| You need access away from the office | Use section 5. |
| You only need a temporary trusted-Wi-Fi test | Use section 6. |
| You want your own independent installation | Follow section 9 first. |

Phones, tablets, Windows PCs, Macs and Linux computers can act as browser clients. The **host installation instructions below are Windows PowerShell instructions**; they are not macOS/Linux shell commands.

### Where the work happens

```text
Your device's browser
  -> authenticated Local RAG server
  -> document retrieval + local Ollama model
  -> answer and source excerpts returned to your device
```

The host must stay powered on, awake and connected. Closing the browser does not shut down the host. The existing installation uses **Neon PostgreSQL**, so documents, extracted text, vectors and saved application records can be stored remotely. Local model execution does not mean all storage is local or that this deployment works offline. A separate local PostgreSQL migration has not been completed.

The latest audit changes are a tested candidate, not a completed production release. They may not yet be committed or available in a fresh GitHub clone. Ask the maintainer for the reviewed revision you should use.

## 2. Connect as a user

### Before you begin

Ask the administrator for:

- The server's **website address**.
- Your **personal Local RAG API key**.
- Access to the documents you need.
- A Tailscale invitation/setup instructions if remote access is used.

Do not request or share the administrator key, database password or `.env` file.

### Steps on any client device

1. Connect to the approved office Wi-Fi, or connect Tailscale as instructed by the administrator.
2. Open your browser: for example Safari, Chrome, Edge or Firefox.
3. Open the exact server address supplied by the administrator.
4. Open **Connection** if the connection dialog does not appear automatically.
5. For **Server address**, use the website's base address with no `/v1` suffix. If already viewing the host's own website, leaving the address blank uses that same website.
6. Paste your personal key into **API key**, then select **Connect**.
7. Select an available response profile, choose a knowledge source and ask a question.
8. Bookmark the website for later use.

There is no normal username/password sign-up screen in this application. The personal key identifies your account. The browser stores that key in session storage; you may need to re-enter it when the browser session ends.

### Which address should you open?

| Where you are | Address |
|---|---|
| On the host itself | `http://127.0.0.1:8000/` |
| On another device on the same Wi-Fi | `http://SERVER-LAN-IP:8000/` after section 6 |
| On a permitted device using Tailscale | The private HTTPS address printed in section 5 |

`127.0.0.1` and `localhost` always mean **the device you are currently using**. They do not point back to the server from your phone. `0.0.0.0` is a listening setting, not a website address.

The previously used LAN address `192.168.10.97` is only a historical example. The administrator must check the host's current address.

## 3. Start an existing Windows host

Administrator/host-owner steps only. Skip these if the application is already running.

### 3.1 Open the correct project directory

Open PowerShell. For the existing project:

```powershell
Set-Location -LiteralPath "C:\Users\Aarushi Gupta\Documents\ChatGPT\LLM Project"
```

On a different host, replace that directory with the folder containing `app.py`, `.env`, `.venv-rag` and `frontend`.

Check the existing process before starting another:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/health/live" -TimeoutSec 5
```

If it returns `status: alive`, do not start a second copy. A connection error means it may be stopped; an occupied port or timeout needs investigation, not indiscriminate process termination.

### 3.2 Check memory

```powershell
.\.venv-rag\Scripts\python.exe -c "import psutil; print('Available RAM:', round(psutil.virtual_memory().available / 1024**3, 2), 'GiB')"
```

The temporary laptop test configuration reserves **2 GiB of available RAM before generation**. This is free RAM, not installed RAM. It does not guarantee that every model will fit after loading. This laptop has previously reached critically low available memory.

On the production Tally host, keep the planned **8 GiB reserve or a stricter measured limit**. Do not copy the lower laptop threshold onto that server. Resource checks and a single worker cannot guarantee zero impact on Tally; test in an approved maintenance window.

### 3.3 Verify Ollama

```powershell
Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
```

If that fails because Ollama is stopped, open a **separate PowerShell window** and run:

```powershell
$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_MAX_LOADED_MODELS = "1"
$env:OLLAMA_KEEP_ALIVE = "1m"
ollama serve
```

Keep the window open. If Ollama is already running, do not launch a duplicate. The one-model limit is conservative for laptop testing; it can increase latency by switching between embedding and chat models. These environment settings affect only the Ollama process launched from this window, not an existing tray process.

### 3.4 Start Local RAG without schema changes

In the project PowerShell window, use the appropriate reserve. The following block is **only for the personal test laptop without Tally**:

```powershell
$env:RUN_MIGRATIONS = "false"
$env:WARM_MODELS = "false"
$env:OFFICE_HOURS_POLICY = "true"
$env:OFFICE_HOURS_START = "00:00"
$env:OFFICE_HOURS_END = "24:00"
$env:MIN_AVAILABLE_RAM_GB = "2"

.\.venv-rag\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

For the Tally host, use `MIN_AVAILABLE_RAM_GB = "8"` instead, or the higher limit approved by its administrator. This implementation accepts `24:00` as the end of its all-day protection window.

These settings are temporary for this PowerShell process. They do not edit `.env`. Migrations and automatic model preloading are disabled. Normal authenticated use can still write chats, account activity and uploads to the configured database; this is not a read-only application mode.

Keep the window open. Open [Local RAG on the host](http://127.0.0.1:8000/).

### 3.5 Verify dependencies

In another PowerShell window:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/health/live" -TimeoutSec 5
Invoke-RestMethod "http://127.0.0.1:8000/health/ready" -TimeoutSec 30
```

Expect an alive process and connected database/Ollama. A healthy readiness response is **not proof that enough RAM is available for generation**; admission checks also run when a request arrives.

## 4. Create users and grant document access

Only the administrator does this. Existing keys should be reused; do not regenerate the master key merely to start the app.

1. On the host, connect using the administrator's existing `RAG_API_KEY` from their securely stored configuration.
2. Open **Access**. The dialog is titled **Team access**.
3. Enter the person's name.
4. Choose **User**, not Administrator, unless elevated access is intentional.
5. Select **Create key**.
6. Copy the displayed key immediately and deliver it through an approved private channel. The raw personal key cannot be retrieved later.
7. In the document-permission section, select the user and a ready document.
8. Select **Grant access**. Repeat for each document they are allowed to read.
9. Have that user connect on their own device and confirm they see only their permitted documents.

An account alone does not automatically grant access to every company document. A successfully connected user with an empty knowledge list may simply need document permissions.

### Lost key or device

Use **Access → Rotate API key** for that account and privately distribute its replacement. Rotation invalidates the old key across all devices using that account. Do not paste keys into shared screenshots, public issues or source code.

This implementation has one active key per account. The same person may use it on their approved devices. Independent per-device revocation requires separate accounts/identities or additional key-management work; do not assume multiple independently revocable keys exist within one account.

## 5. Private remote access with Tailscale

Recommended access route for this guide. Tailscale network access and Local RAG document permissions are separate controls; configure both. Check the service's current plan and organizational requirements rather than assuming every business use is free.

### Host administrator

1. Install [Tailscale](https://tailscale.com/download) on the host and sign in to the approved private network.
2. Keep Local RAG running on `127.0.0.1:8000` as in section 3.
3. In a new PowerShell window, run:

```powershell
tailscale status
tailscale serve status
```

If HTTPS port 443 is already serving another application, coordinate with its owner before changing it.

4. Configure private HTTPS access:

```powershell
tailscale serve --bg --https=443 http://127.0.0.1:8000
tailscale serve status
```

Complete any HTTPS enablement prompt with the network administrator. Copy the exact printed HTTPS address. Serve proxies the loopback app and `--bg` keeps its configuration persistent; the application itself must still be running. See the [official Serve reference](https://tailscale.com/docs/reference/tailscale-cli/serve).

5. If `.env` has a nonempty `ALLOWED_HOSTS`, append the printed hostname, without `https://` or a path, while retaining the existing approved entries. Restart Local RAG after a configuration change; warn active users first.
6. Approve/invite the intended users/devices and restrict network access to the intended host/service. Do not share the administrator's sign-in credentials.
7. Give each person the HTTPS address and their own Local RAG key.

### Client device

1. Install Tailscale from its official download page or your mobile app store.
2. Join the approved network using your invitation/account. Your own devices can use your own account; colleagues should use their own authorized identities.
3. Turn Tailscale on.
4. Open the supplied HTTPS address in a browser.
5. Connect with your personal Local RAG key using section 2.

Use **Serve**, not **Funnel**, for this private setup. Do not add router forwarding for ports 8000, 11434, 11435 or 5432.

To remove only this Serve listener later, first confirm its ownership with `tailscale serve status`, then use:

```powershell
tailscale serve --bg --https=443 http://127.0.0.1:8000 off
```

This interrupts remote access through that listener but does not delete application data. See the [Serve disable instructions](https://tailscale.com/docs/reference/tailscale-cli/serve#disable-tailscale-serve).

## 6. Same-Wi-Fi access

Temporary testing on a trusted LAN only. HTTP does not encrypt API keys, questions or answers. Prefer section 5 for ongoing use. Both client and host must be on a network that allows device-to-device connections; guest Wi-Fi often does not.

### 6.1 Find the host's current LAN address

On the host:

```powershell
Get-NetIPConfiguration
Get-NetConnectionProfile
```

Find the IPv4 address of the active Wi-Fi/Ethernet adapter with the office gateway. Do not use a loopback, VPN, virtual-adapter or `169.254.*` address. Reserve the chosen host address in the router's DHCP settings if your network administrator approves.

### 6.2 Restart just Local RAG for LAN access

**This interrupts active chats.** In its running PowerShell window press `Ctrl+C`. Do not stop Tally, PostgreSQL or unrelated Python processes.

In that same window, retain the resource/migration settings from section 3, then run:

```powershell
.\.venv-rag\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
```

This listens on all IPv4 interfaces. The following firewall rule restricts its new allowance, but existing broader firewall rules may also permit access; have the administrator review them.

### 6.3 Add a narrowly scoped firewall rule

Open a separate **Administrator PowerShell** window:

```powershell
if (-not (Get-NetFirewallRule -Name "LocalRag-LAN-8000" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name "LocalRag-LAN-8000" -DisplayName "Local RAG LAN 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private -RemoteAddress LocalSubnet
}
```

The active network must be an approved **Private** network for this rule to apply. Do not relabel an untrusted network as Private to make the app work. On a managed Domain network, ask IT for the equivalent scoped rule; do not disable Windows Firewall.

If `ALLOWED_HOSTS` is configured, append the LAN IP to its existing entries and restart the app. Same-origin browser access does not require wildcard CORS or a separate frontend server.

### 6.4 Open from your phone or another computer

Replace `SERVER-LAN-IP` with the address found in 6.1:

```text
http://SERVER-LAN-IP:8000/
```

For example, **only if the host currently has this address**:

```text
http://192.168.10.97:8000/
```

Connect using your personal key. On another Windows computer, the administrator can diagnose network reachability with:

```powershell
$serverIp = Read-Host "Enter the host's current LAN IPv4 address"
Test-NetConnection -ComputerName $serverIp -Port 8000
```

### 6.5 End the LAN test

Warn users, stop Local RAG with `Ctrl+C`, then restart with `--host 127.0.0.1` as in section 3. Disable only the test rule in Administrator PowerShell:

```powershell
Disable-NetFirewallRule -Name "LocalRag-LAN-8000"
```

The rule remains recoverable. For a later approved LAN test, re-enable it with `Enable-NetFirewallRule -Name "LocalRag-LAN-8000"` and repeat the listener checks. Do not expose Ollama or PostgreSQL to make browser access work.

## 7. Chat and use documents

1. Connect with your key.
2. Choose an installed profile. Start with **Fast** for the small test model. **Balanced** may be unavailable if its model is not installed. Profile names do not guarantee different models or better accuracy.
3. Select one document for a focused question, or the available collection for a broader search.
4. Ask one specific question, using names, identifiers or dates where relevant.
5. Open the source cards and check the supporting excerpts/pages.
6. If the answer is withheld or says information is missing, check document permissions, indexing state and whether the actual evidence answers your question. Do not treat the ranking score as a probability that the answer is correct.

### Add a harmless test document

For your first test, use a non-sensitive TXT file with a short fact, such as `The approved sample limit is 42 units.` Upload it through the document/knowledge panel, wait until indexing reports **ready**, select it and ask what the approved sample limit is. This is a functional check, not an accuracy guarantee.

TXT, Markdown, CSV, JSON, text-based PDF, DOCX and XLSX are supported by the main environment. Images and scanned PDFs additionally require the separately configured OCR environment. A new installation without OCR should begin with TXT or a text-based PDF. Do not assume installing the main requirements installs PaddleOCR too.

Uploads/indexing use host resources and write to the configured database. Run large imports outside production hours. Never upload company documents to an unapproved host/database. Deleting a document removes searchable data; do not use deletion as a troubleshooting shortcut.

Some answers are deliberately buffered until citation checks finish. A blank answer area while the app says it is working is not necessarily a frozen connection. Additional requests can queue behind the current request.

## 8. Connect scripts and API applications

Browser users can skip this section. Programmers use the same server and their own personal key.

| Setting | Value |
|---|---|
| Website / Connection dialog address | Server origin, without `/v1` |
| API base URL | Server origin plus `/v1` |
| Chat endpoint | `POST /v1/chat/completions` |
| Authentication header | `X-API-Key: YOUR_PERSONAL_KEY` |
| Initial model | `gemma3:1b-it-qat`, if installed and allowed |
| Optional initial profile | `fast` |

The chat JSON follows an OpenAI-style structure, but **Bearer-only clients are not automatically compatible**. This code authenticates with `X-API-Key`. A third-party application must allow that custom header; otherwise use the browser or an administrator-approved adapter. Do not disable authentication to accommodate a client.

Typing `/v1/chat/completions` in a browser sends GET, not POST; a method error is expected. `/v1` is not the chat website.

### Python example from another computer

Install Python and the requests package only if you want this script-based access:

```powershell
python -m pip install requests
```

Save the following as `ask_local_rag.py`. Run it with `python ask_local_rag.py`:

```python
from getpass import getpass
import requests

base = input("Server website address, without /v1: ").strip().rstrip("/")
key = getpass("Your personal Local RAG key: ")
question = input("Question about your permitted documents: ")

response = requests.post(
    f"{base}/v1/chat/completions",
    headers={"X-API-Key": key},
    json={
        "model": "gemma3:1b-it-qat",
        "profile": "fast",
        "messages": [{"role": "user", "content": question}],
        "stream": False,
        "max_tokens": 120,
        "save": False,
        "use_cache": False,
    },
    timeout=360,
)
if response.status_code != 200:
    print("Request failed:", response.status_code, response.text)
else:
    result = response.json()
    print(result["choices"][0]["message"]["content"])
    for source in result.get("sources", []):
        print("Source:", source.get("filename"), "Page:", source.get("page_number"))
```

Use the private HTTPS address for normal remote use. Do not save the key inside the script or print it. `save=False` disables saving this conversation; it is not a promise that no authentication/activity records are updated.

## 9. Install a new Windows host

**Skip this entire section when connecting to the existing server.** This creates a separate installation. It does not transfer the existing documents or users, and it must not initialize or modify the production database by accident.

### 9.1 Prerequisites

- A Windows host you are authorized to administer, with adequate free RAM, disk space and network access.
- Python 3.12; this repository was tested locally with 3.12.10.
- Node.js and npm; the tested host uses Node 24.16.0. The installed Vite package declares Node `^20.19.0 || >=22.12.0`.
- Git, or a maintainer-provided release ZIP.
- Ollama for Windows.
- A **separate, approved PostgreSQL database with pgvector support**, or administrator-provided access to a prepared application database.

Use official installers: [Python](https://www.python.org/downloads/windows/), [Node.js](https://nodejs.org/en/download), [Git](https://git-scm.com/downloads/win), [Ollama](https://ollama.com/download/windows). Ollama's Windows installation/runtime details are documented in its [Windows guide](https://docs.ollama.com/windows). Do not assume laptop installation steps have been production-tested on Windows Server/Tally.

Allow additional disk space for model downloads, documents, build dependencies and backups. An 8 GB laptop can run out of free memory even with a small model; installed RAM is not sufficient evidence of safe capacity.

### 9.2 Obtain the reviewed source

For a published repository revision:

```powershell
git clone https://github.com/aarushi787/local-rag.git C:\LocalRAG
Set-Location -LiteralPath C:\LocalRAG
```

If `C:\LocalRAG` already exists, choose another empty destination; do not delete or overwrite it. For a release ZIP, extract it to a new folder and open PowerShell there. Use the maintainer's approved commit; a fresh clone may not include unpushed audit fixes described in this guide.

### 9.3 Install application dependencies

```powershell
py -3.12 -m venv .venv-rag
.\.venv-rag\Scripts\python.exe -m pip install --upgrade pip
.\.venv-rag\Scripts\python.exe -m pip install -r requirements-rag.txt

Push-Location frontend
npm.cmd ci
npm.cmd run build
Pop-Location
```

Using the virtual environment's executable avoids PowerShell activation-policy changes. If a pinned package is unavailable, stop and give the maintainer the installation error; do not silently replace dependency versions. `npm ci` requires the repository's lockfile.

### 9.4 Install only the initial models

Start Ollama, then:

```powershell
ollama pull embeddinggemma
ollama pull gemma3:1b-it-qat
ollama list
```

Do not initially pull 4B/12B models, rerankers or BGE-M3 on a memory-constrained host. Changing the embedding model without rebuilding a compatible index is not a valid upgrade.

### 9.5 Configure a separate database and secrets

For a new Neon installation, create your own project/database in its console, open **Connect**, and obtain that database's PostgreSQL connection URL. Ensure it supports pgvector and that the initialization role can create the extension/schema. This route stores application data remotely and requires network connectivity.

Alternatively, have an administrator provision a local PostgreSQL/pgvector instance. The repository contains `local-infrastructure/docker-compose.yml`, but Docker/server support and safe deployment must be established separately. Do not migrate the existing Neon data just to test a new device.

Copy the example configuration **only if `.env` does not already exist**:

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
notepad .env
```

Generate a new administrator key locally:

```powershell
.\.venv-rag\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

This intentionally displays a secret on your own screen. Store it in a password manager and the new host's `.env`; do not include it in screenshots or shared logs.

Edit the matching lines in `.env` rather than adding duplicates:

```dotenv
DATABASE_URL=REPLACE_WITH_THIS_NEW_DATABASE_CONNECTION_URL
RAG_API_KEY=REPLACE_WITH_YOUR_NEW_RANDOM_ADMIN_KEY
REQUIRE_API_KEY=true
OLLAMA_URL=http://127.0.0.1:11434
EMBEDDING_OLLAMA_URL=http://127.0.0.1:11434
EMBEDDING_MODEL=embeddinggemma
CHAT_MODEL=gemma3:1b-it-qat
AUTO_MODEL_ROUTING=false
RUN_MIGRATIONS=false
WARM_MODELS=false
OLLAMA_KEEP_ALIVE=1m
OFFICE_HOURS_POLICY=true
OFFICE_HOURS_START=00:00
OFFICE_HOURS_END=24:00
MIN_AVAILABLE_RAM_GB=8
STRICT_CITATION_GATE=true
ALLOWED_ORIGINS=
ALLOWED_HOSTS=127.0.0.1,localhost
GOOGLE_DRIVE_FOLDER_URL=
```

Only for a personal, non-Tally test laptop, the administrator may choose the 2 GiB reserve described in section 3. Do not turn resource protection off to force an oversized model to run. Leave Drive synchronization unconfigured until an authorized owner explicitly sets it up.

### 9.6 Initialize the new database once

**Database-write warning:** the following applies schema changes and can alter existing RAG records. Use it only for the new, explicitly selected empty database or an administrator-approved migration with a tested backup. Never point this at the current production database merely to follow a tutorial.

In the project directory:

```powershell
$env:RUN_MIGRATIONS = "true"
$env:WARM_MODELS = "false"
.\.venv-rag\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

Wait for startup and verify readiness from a second window. If initialization fails, resolve the permission/extension error before continuing; do not blindly retry against an uncertain database.

Stop this app with `Ctrl+C`, then disable migrations and start normally:

```powershell
$env:RUN_MIGRATIONS = "false"
.\.venv-rag\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

Keep `RUN_MIGRATIONS=false` in `.env` for later starts. The existing least-privilege SQL requires review for newer schema objects; have an administrator verify the runtime role before production use rather than assuming a script grants exactly the necessary permissions.

Connect locally with the new admin key, upload a harmless test document, create a regular user and grant access. Only then configure section 5 or 6.

## 10. Restart, stop and maintain the host

- Warn users before stopping or restarting the API; active requests may be interrupted.
- In the foreground API window, `Ctrl+C` stops that app. Restart with the appropriate command from section 3 or 6. Closing that terminal normally stops its process.
- `.env` changes require an app restart. Process-level `$env:` settings override `.env`; use a fresh PowerShell window when switching back to saved settings.
- Keep the host awake while serving. Follow company power/security policy; do not change Tally/server policies without approval.
- Keep the administrator key, personal keys, `.env`, database backups and document exports private.
- Use approved database backups; copying just the code folder does not back up Neon documents, accounts or chats.
- Do not run schema initialization, bulk ingestion, evaluation or model downloads during production work without checking resource impact.

### Optional automatic startup

After manual startup and safety testing succeed, an administrator can inspect and run:

```powershell
.\scripts\install-startup-task.ps1
```

This registers/replaces the named **Local RAG Server** task for startup after user sign-in. It is not a Windows service that is guaranteed to run before anyone logs in. It uses `.env`, not temporary settings from section 3. Review those saved settings first. The existing launcher may allow two resident Ollama models when it starts Ollama, so review it before enabling startup on a low-memory laptop. It starts FastAPI on loopback; use Tailscale for remote access.

To remove just that startup task later:

```powershell
.\scripts\remove-startup-task.ps1
```

This changes scheduled startup, not database contents. Do not create duplicate tasks or install a second independent launcher.

## 11. Troubleshooting

| Problem | Check / safe next step |
|---|---|
| Phone cannot open localhost | Use the host's LAN IP or private HTTPS address; localhost refers to the phone. |
| Site cannot be reached on Wi-Fi | Check host awake, current IP, LAN listener, firewall profile, guest-network isolation and allowed hosts. |
| Works locally but not remotely | Confirm Tailscale is connected on both devices, user/device access is approved, and Serve points to the running host app. |
| Invalid host / HTTP 400 | Append the exact approved IP/hostname to ALLOWED_HOSTS and restart; do not remove unrelated approved entries. |
| HTTP 401 / unauthorized | Re-enter your personal key; ask the admin whether it was rotated, expired or disabled. Use X-API-Key for scripts. |
| Login works but no documents | Ask the admin to grant document access; confirm indexing finished. |
| HTTP 503 about RAM / Tally protection | Free memory safely or use the adequately provisioned server; wait for cooldown. Do not lower production protection to hide the error. |
| HTTP 429 / queue full | Wait and retry; avoid repeatedly submitting the same question. A per-user or shared queue limit may apply. |
| `/v1/chat/completions` shows a method error | It accepts POST with JSON and a key, not browser GET. Open `/` for the UI. |
| Balanced unavailable / model error | Select an installed permitted profile; the admin can inspect `ollama list`. Do not choose the embedding model for chat. |
| Database disconnected | Host owner checks database availability/network and its private URL. Never send database credentials to clients. |
| OCR unavailable | Start with text documents; have the administrator configure the separate OCR environment before scanned-file ingestion. |
| Answer withheld despite source text | The conservative citation validator can reject valid paraphrases; inspect excerpts, ask a specific question and report the example to the administrator. |
| Reply takes several seconds | Check database/network delay, model cold start, queue, memory and output length. Switching to a phone does not accelerate host inference. |
| Port 8000 already in use | Check the existing app first; do not kill every Python process or stop accounting services. |
| Browser forgets the key | Re-enter it from your password manager; session storage is not permanent key storage. |
| New clone behaves differently | Confirm the maintainer's approved revision; local uncommitted changes are not included in GitHub clones. |

## 12. Acceptance checklist

Before inviting more people, verify:

- [ ] Local website loads and `/health/ready` reports connected dependencies.
- [ ] Host resource reserve is appropriate and generation completes without memory pressure.
- [ ] A normal user connects with their own key, not the admin key.
- [ ] That user can see an explicitly granted test document.
- [ ] A document withheld from that user is not accessible through their account.
- [ ] A grounded answer is checked against its cited excerpt; missing evidence produces a useful refusal.
- [ ] A second approved device can connect through the chosen network route.
- [ ] Remote HTTPS is tested from outside office Wi-Fi when remote use is required.
- [ ] Two users are tested without stressing the host; queue behavior is understood.
- [ ] Tally remains responsive in an administrator-approved test before any co-hosted deployment.
- [ ] Reboot/sign-in recovery is tested if automatic startup is enabled.
- [ ] Backups, access revocation and ownership of the host are documented.

Code tests and one successful chat do not establish production accuracy. The audit's human-reviewed evaluation and live performance gates remain separate requirements; see `docs/UPGRADE_CHANGELOG.md` and `reports/comparison.md`.

## 13. Quick reference

### For a person who only wants to use the app

1. Get the website address and your personal key from the administrator.
2. Join the approved Wi-Fi or connect Tailscale.
3. Open the website in your browser.
4. Open Connection, enter the base address if needed and paste your key.
5. Choose an available profile and permitted document.
6. Ask a question and check the sources.

### For the host administrator

1. Start Ollama on loopback if it is not already running.
2. Start Local RAG with migrations/preloading off and appropriate memory protection.
3. Check liveness/readiness.
4. Create individual user keys and grant specific document access.
5. Choose Tailscale HTTPS, or a temporary scoped LAN test.
6. Share only the website address and each person's own key.

**Website:** `/` · **API base:** `/v1` · **Chat:** `POST /v1/chat/completions` · **Authentication:** `X-API-Key`

Never forward the app, Ollama or database ports through the internet router. Never distribute the host's `.env` file to users.
