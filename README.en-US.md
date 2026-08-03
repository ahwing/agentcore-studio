

# AgentCore Studio

> Drag-and-drop orchestration · Deploy your AI Agent with one click ｜ From canvas to cloud in minutes
>
> 🌐 [English](README.en.md) ｜ Chinese

**AgentCore Studio** is a visual orchestration workspace designed for Amazon Bedrock AgentCore. Drag and drop core components like Runtime / Harness, Memory, Gateway, Identity, Observability, and Policy onto the canvas, along with built-in tools like Code Interpreter and Browser, and MCP tools / Skills mounted under the Gateway, to assemble an AI Agent like building blocks. Every configuration change **generates real, deployable artifacts in real-time** (entry code, deployment scripts, IAM policies, component registry) and instantly registers them in the Registry. Once configured, **deploy to the cloud with one click** to truly deploy on AWS, then validate by chatting directly with the Agent in the built-in **Playground**: get second-level feedback locally via live Bedrock connections, and ensure trustworthy execution in the cloud.

![AgentCore Studio UI](ui.png)

## Architecture

![AgentCore Studio Architecture](architecture.png)

> Developers orchestrate via drag-and-drop in the Studio (deployable on App Runner / EC2 / ECS / EKS / locally) → generated artifacts are deployed via CI/CD (CodeBuild → S3 → ECR) → the Agent Runtime in Amazon Bedrock AgentCore orchestrates Memory, Identity, Policy, Observability, Gateway tool layers, and built-in sandbox tools. Editable source file available at [`architecture.drawio`](architecture.drawio).

## Features

### 🎨 Visual Orchestration
- Drag and drop to orchestrate all AgentCore components; click a node to pop up an editing panel; dropdown toggles trigger field linkage (e.g., Skill source inline/path/upload, Identity inbound/outbound, Gateway IAM/JWT, Policy Cedar/natural language, Runtime code source ECR/S3)
- ⚙️🚀 **Dual Core: Runtime & Harness**: Choose between Runtime (includes orchestration code, container/artifact deployment) and Harness (declarative, AgentCore-managed agent loop, immutable versions + named endpoint instant rollback), switch on demand
- ✨ **AI-Generated Canvas (NL→Canvas)**: Describe the Agent you want in one sentence to auto-generate an **editable canvas** with nodes and connections; continue drag-and-drop fine-tuning afterward with automatic pre-flight validation
- 🧠 **Deep Generation**: 4-step intelligent orchestration (requirement breakdown → component configuration → System Prompt → validation), SSE streaming real-time progress feedback, auto-generates complete deployable artifacts + selection rationale + pre-deployment report; apply generated results to the canvas with one click
- ⏰ **Scheduled Triggers (EventBridge Scheduler)**: Auto-introduced when requirements include periodic execution; deployment script generates `aws scheduler create-schedule` + IAM Role, supports cron/rate expressions
- 📦 **One-Click Scenario Templates**: Minimal chat / Customer service (with tools) / Data analytics / Full stack, fills the canvas in seconds
- 🔗 Accurately connected relationships (Runtime as the hub, MCP/Skill mounted under Gateway)

### 🎮 Playground: Local second-level validation → Iteration loop
- **Local direct connection to Bedrock `converse` for real model responses** / AWS cloud as two sources; source status is **transparently labeled**: Local·Live Run (executes your orchestrated tools) / Local·Model (direct model connection, no tool execution) / Local Simulated / AWS Cloud
- **System Prompt changes take effect instantly** — the system prompt is passed to the Agent with every conversation; tweak a prompt and see new results immediately without redeployment
- 🔍 **Call Transparency (Trace)**: Expand each response to view tool invocations (inputs/results), token usage, latency, and model — local and cloud share a single data source
- ⚖️ **A/B Comparison**: Run baseline vs. candidate System Prompts side-by-side on the same input, directly judging whether changes improve or degrade performance
- 📋 **Test Suite**: Save a set of inputs to run all at once; results are **labeled with changes compared to the last run** (new/changed/unchanged) for lightweight regression testing
- 💾 **Persistent Chat History**: Conversations and history for each Agent are saved locally, surviving page refreshes

### 📄 Real-time Artifacts & Deployment
- Generates `agentcore_entry.py` / `deploy.sh` / `iam-policy.json` / `requirements.txt` / `registry.json` in real-time; Registry instantly registers all components, built-in tools, and MCP/Skills
- ✅ **Pre-flight Validation**: Beyond completeness checks, performs **cross-node semantic/region/security** validation (e.g., `web_search` only in `us-east-1`, cross-region knowledge bases, Policy ENFORCE without permits locking everything, public internet exposure risks, etc.); status bar shows "risk" in real-time during design and intercepts with warnings before deployment
- 🚀 **Deployment Pipeline Trace**: Shows component deployment paths during publishing, lighting up sequentially (pending → in progress → ✓); background task + polling progress (unaffected by streaming timeouts), real-time logs + deployment timing heartbeat
- ⚡ **Incremental Deployment (Three States)**: Fingerprint-based determination — artifact/code changes → full rebuild; control plane config changes only (protocol/timeout/env vars/description, etc.) → `update-agent-runtime` second-level update (reuses artifacts, preserves ARN); no changes → skipped. Identity / MCP Target / Policy / Memory / Gateway all support fast in-place updates
- ☁️ **One-Click Cloud Deployment**: Automatically publishes locally first if not already done, then truly deploys to AWS Bedrock AgentCore (in-place update, old version continues serving during rebuild) and switches to Playground to view real-time progress; auto-detects ready cloud Agents as a demo "fallback"

### 🧩 Multi-Agent & Reuse
- **Multi-Agent Orchestration**: Pull published agents from the cloud, generate an orchestrator Agent with one click — Supervisor (master wraps child Agents as tools for on-demand invocation) or A2A (collaborates with peer Agents via `InvokeAgentRuntime` transparently forwarding JSON-RPC `message/send`, A2A mode only lists agents deployed with `--protocol A2A`); canvas automatically draws master↔child Agent relationships
- **Import Existing Agents for Continued Editing**: Archives the entire canvas configuration to an S3 state bucket (`specs/<name>.json`) upon deployment; when importing, pulls the cloud agent list and cross-labels "importable", click to read back configuration and **rebuild an editable canvas**, modify, and redeploy. Only works for agents published via Studio

> Details: Model IDs automatically append cross-region inference configuration prefixes (`us.`/`eu.`/`apac.`) based on region; default region is `us-west-2`, default model is Claude Sonnet 4.5; automatically clears residual cross-region toolkit local state when switching deployment regions.

## Local Development
```bash
python3 server.py            # Opens http://127.0.0.1:8799
# Custom port / Enable access password:
PORT=9000 STUDIO_PASSWORD=yourpass python3 server.py
```
> The backend executes the generated code and invokes the `agentcore` CLI, binding only to `127.0.0.1` by default. Do not expose it to the public internet without authentication.

## Files
| File | Description |
|---|---|
| `index.html` | Single-file frontend (fonts inlined, works offline) |
| `server.py` | Zero-dependency backend (publishing / Playground / deployment / cloud invocation / NL→Canvas / deep generation relay) |
| `deep_generate.py` | Deep generation engine (4-step LLM orchestration + parallel optimization + SSE streaming progress) |
| `Dockerfile` | Container image (includes agentcore CLI + AWS CLI + zip) — optional, for packaging to any container platform |
