# Xeon Private AI Server Deployment Kit

This folder deploys the Ollama + Open WebUI design on the intended Windows
Server 2025 host. It is deliberately separate from the existing laptop RAG
application, which uses Ollama on port 8080 and FastAPI on port 8000.

Every mutating script checks for all three target-server facts before changing
the machine:

- Windows Server 2025
- Intel Xeon 6315P
- at least 30 GB usable RAM

Do not use `-AllowNonTargetHost` during the real installation. That switch exists
only for isolated script testing.

## Before copying this folder to the server

Download these items from their official sources and copy them to the indicated
locations on the server:

1. Ollama Windows installer: <https://ollama.com/download/windows>
2. 64-bit NSSM 2.24-101 or newer: `C:\AI\bin\nssm.exe`
3. `uv.exe`: `C:\AI\bin\uv.exe`
4. Tailscale Windows installer: <https://tailscale.com/download/windows>

The first three installation stages need an elevated PowerShell window.
No script opens a router port. The Tailscale script exposes only Open WebUI over
private tailnet HTTPS.

## 1. Preflight

Run while Tally is open:

```powershell
Set-Location C:\Path\To\server-build
.\00-preflight.ps1
```

Stop if the target-server guard, disk-space check, or hardware query fails.
The report is written to `artifacts\preflight.json`.

## 2. Capture the Tally baseline

This changes no services and generates no AI load. During the five-minute
capture, perform ten representative Tally operations and record their times.

```powershell
.\50-tally-load-test.ps1 -Mode Baseline -DurationSeconds 300
```

## 3. Install and configure Ollama

Run the official Ollama installer. Then apply the server guardrails:

```powershell
.\10-configure-ollama.ps1
```

Restart Ollama so it inherits the new machine environment. Then download only
the office-hours models:

```powershell
.\10-configure-ollama.ps1 -PullOfficeModels
```

The script enforces:

- `127.0.0.1:11434`
- one parallel request
- one loaded model
- 4,096-token context
- four queued requests maximum
- a two-minute model keep-alive

Do not download the 12B model until the 1B and 4B acceptance tests pass. Its
separate after-hours command is:

```powershell
.\10-configure-ollama.ps1 -PullAfterHoursModel
```

### Optional unattended Ollama service

After the tray-based pilot passes, download the official standalone Ollama ZIP,
extract `ollama.exe` to `C:\AI\Ollama`, and perform the service cutover in an
approved AI maintenance window:

```powershell
.\11-install-ollama-service.ps1 -ConfirmCutover
```

The script stops only existing Ollama processes, installs a delayed-start
LocalService through NSSM, applies below-normal CPU priority, and refuses to
leave the service running if port 11434 is not loopback-only.

Measure real generation speed after each model is installed:

```powershell
.\12-benchmark-ollama.ps1 -Model gemma3:1b-it-qat -AcknowledgeProductionLoadRisk
.\12-benchmark-ollama.ps1 -Model gemma3:4b-it-qat -AcknowledgeProductionLoadRisk
```

## 4. Install Open WebUI as a service

Ensure `C:\AI\bin\uv.exe` and `C:\AI\bin\nssm.exe` exist, then run:

```powershell
.\20-install-openwebui.ps1
```

Open <http://127.0.0.1:8080> on the server and create the first administrator
account. Leave ordinary users pending. In the admin interface:

1. Confirm the Ollama connection is `http://127.0.0.1:11434`.
2. Enable API keys only for approved users.
3. Restrict API-key endpoints to `/api/chat/completions`.
4. Disable public signup after onboarding.

## 5. Enable private HTTPS

Install Tailscale, sign in, and confirm the account/licence is appropriate for
commercial use. Then run:

```powershell
.\30-enable-tailscale.ps1
```

The command prints the private `https://...ts.net` address. Do not enable
Tailscale Funnel and do not port-forward 8080 or 11434.

## 6. Verify

Local verification:

```powershell
.\40-verify.ps1
```

Authenticated end-to-end verification:

```powershell
$serverUrl = 'https://SERVER-NAME.TAILNET-NAME.ts.net'
$userKey = Read-Host 'Paste a temporary Open WebUI API key'
.\40-verify.ps1 -ApiBaseUrl $serverUrl -ApiKey $userKey
Remove-Variable userKey
```

## 7. Tally protection tests

Run only in an approved test window while a user performs and times the same ten
Tally operations used for the baseline.

```powershell
.\50-tally-load-test.ps1 -Mode Gemma1B -DurationSeconds 300 -AcknowledgeProductionLoadRisk
.\50-tally-load-test.ps1 -Mode Gemma4B -DurationSeconds 300 -AcknowledgeProductionLoadRisk
```

Acceptance thresholds:

- median Tally operation time increases by no more than 10%
- worst Tally operation time increases by no more than 20%
- no Tally error, disconnect, save failure, or database warning
- at least 8 GB RAM remains available

If 4B fails, permit only 1B during office hours. If 1B fails, do not co-host the
AI workload on the Tally server.

## 8. Back up Open WebUI

Use a separate disk or protected network destination. The backup briefly stops
only Open WebUI so its SQLite and Chroma files are consistent:

```powershell
.\90-backup-openwebui.ps1 -BackupTarget 'E:\AI-Backups' -AcknowledgeAiDowntime
```

The script restarts Open WebUI in a `finally` block and prints the archive's
SHA-256 checksum.

## RAG comes after the infrastructure gate

Do not enable document ingestion or a reranker during this first build. Once
the server passes reboot, access, API and Tally tests, the next stage will add:

1. `ollama pull bge-m3`
2. Open WebUI local Chroma with one worker
3. controlled document extraction and re-index testing
4. hybrid retrieval
5. `BAAI/bge-reranker-v2-m3`, initially after hours only

That sequencing prevents OCR, embedding and reranking CPU spikes from being
introduced before the base chat workload is proven safe.
