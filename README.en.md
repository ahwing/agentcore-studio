# AgentCore Studio

> Drag, orchestrate, ship your AI Agent in one click ｜ From canvas to cloud in minutes
>
> 🌐 English ｜ [中文](README.md)

**AgentCore Studio** is a visual orchestration workbench for Amazon Bedrock AgentCore. On the canvas you drag in core components — Runtime / Harness, Memory, Gateway, Identity, Observability, Policy — plus the Code Interpreter and Browser built-in tools and the MCP tools / Skills mounted under a Gateway, assembling an AI Agent like building blocks. Every configuration change **generates real, deployable artifacts in real time** (entry code, deploy script, IAM policy, component registry) and registers them instantly in the Registry. When you're done, **publish to the cloud in one click** for a real deployment to AWS, then chat with the Agent directly in the built-in **Playground** to verify it: locally wired to real Bedrock for sub-second feedback, and trustworthy when running in the cloud.

## Architecture

![AgentCore Studio architecture](architecture.png)

> Developers orchestrate by dragging in Studio (deployable on App Runner / EC2 / ECS / EKS / locally) → the generated artifacts are deployed via CI/CD (CodeBuild → S3 → ECR) → the Agent Runtime in Amazon Bedrock AgentCore drives Memory, Identity, Policy, Observability, the Gateway tool layer, and the built-in sandbox tools. The editable source is in [`architecture.drawio`](architecture.drawio).

## Features
- 🎨 Visually drag-and-drop all AgentCore components; click a node to edit it in a popover, with field interlocks on dropdown change (e.g. Skill source inline/path/upload, Identity inbound/outbound, Gateway IAM/JWT, Policy Cedar/natural-language, Runtime code source ECR/S3)
- ⚙️🚀 **Dual hub — Runtime or Harness**: Runtime (ships its own orchestration code, deployed as a container/artifact) or Harness (declarative, AgentCore-managed agent loop, with immutable versions + named endpoints for instant rollback) — pick one, switch as needed
- 🧩 **Multi-agent orchestration**: pull already-published agents from the cloud and generate an orchestrator Agent in one click — Supervisor (the controller wraps each sub-agent as a tool and calls it on demand) or A2A (collaborate with peer agents by passing JSON-RPC `message/send` through `InvokeAgentRuntime`; A2A mode only lists agents deployed with `--protocol A2A`). The canvas automatically draws the orchestrator↔sub-agent relationships
- 📥 **Import an existing Agent to keep editing**: on publish, the entire canvas configuration is archived to the S3 state bucket (`specs/<name>.json`); on import, Studio pulls the cloud agent list and cross-marks which are "importable", then one click reads the config back and **rebuilds an editable canvas** so you can tweak and re-publish. Works only for agents published by Studio (other agents' logic is sealed inside the container and can't be recovered from the control plane)
- 📦 **One-click scenario templates**: minimal chat / customer support (with tools) / data analysis / the full stack — fill the canvas in seconds and see it work
- 🔗 Accurately-related edges (Runtime is the hub; MCP/Skill hang under the Gateway)
- 📄 Generates `agentcore_entry.py` / `deploy.sh` / `iam-policy.json` / `requirements.txt` / `registry.json` in real time
- 📚 The Registry logs all components, built-in tools, and MCP/Skills in real time
- 🎮 Playground chat: **locally connects straight to Bedrock `converse` for real model replies** (real when credentials exist, otherwise falls back to simulation) / or the AWS cloud source; **System Prompt edits take effect instantly** — the system prompt is passed to the Agent on every turn, so tweaking one line shows the new behavior immediately, no redeploy
- 🚀 **Publish pipeline trace**: when publishing to the cloud it shows the component publish path, lighting up step by step (pending → in progress → ✓), ending with "all published"; runs as a background job + progress polling (immune to streaming timeouts), with live logs and a deploy-timer heartbeat
- ⚡ **Incremental publish (three states)**: each component is judged by fingerprint — artifact/code changed → full rebuild; control-plane config only (protocol/timeout/env vars/description, etc.) → `update-agent-runtime` second-level update (reuses the existing artifact, no rebuild, keeps the ARN); unchanged → skipped. Identity / MCP Target / Policy / Memory / Gateway all support in-place fast updates
- ✅ Smart validation: incompletely-configured components are automatically **skipped (not published)** (only a misconfigured Runtime blocks), and the status bar shows "configured / total"
- ☁️ **One-click publish to the cloud**: if it hasn't been published locally it auto-publishes first, then does a real deployment to AWS Bedrock AgentCore (in-place update — the old version keeps serving during the rebuild) and switches to the Playground to watch live progress; auto-detects an already-ready cloud Agent as a demo fallback

> Details: model IDs automatically get the cross-region inference profile prefix per region (`us.`/`eu.`/`apac.`); default region `us-west-2`, default model Claude Sonnet 4.5; switching deploy region auto-cleans toolkit local state left over from another region.

## Run locally
```bash
python3 server.py            # open http://127.0.0.1:8799
# custom port / enable access password:
PORT=9000 STUDIO_PASSWORD=yourpass python3 server.py
```
> The backend executes the generated code and calls the `agentcore` CLI. It binds to `127.0.0.1` only by default — do not expose it to the public internet without authentication.

## Files
| File | Description |
|---|---|
| `index.html` | Single-file frontend (fonts inlined, works offline) |
| `server.py` | Zero-dependency backend (publish / Playground / deploy / cloud invocation) |
| `Dockerfile` | Container image (bundles agentcore CLI + AWS CLI + zip) — optional, for packaging onto any container platform |
