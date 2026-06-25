# AgentCore Studio

> 拖拽编排 · 一键上线你的 AI Agent ｜ From canvas to cloud in minutes
>
> 🌐 [English](README.en.md) ｜ 中文

**AgentCore Studio** 是面向 Amazon Bedrock AgentCore 的可视化编排工作台。在画布上拖拽 Runtime / Harness、Memory、Gateway、Identity、Observability、Policy 等核心组件，以及 Code Interpreter、Browser 内置工具和挂载在 Gateway 下的 MCP 工具 / Skill，像搭积木一样组装一个 AI Agent。每次配置都会**实时生成真实可部署的产物**（入口代码、部署脚本、IAM 策略、组件注册表），并在 Registry 中即时登记。配置完成后**一键发布到云端**真实部署到 AWS，再在内置 **Playground** 里与 Agent 直接对话验证：本地接真实 Bedrock 秒级反馈、云端运行真实可信。

## 架构

![AgentCore Studio 架构图](architecture.png)

> 开发者通过 Studio（可部署在 App Runner / EC2 / ECS / EKS / 本地）拖拽编排 → 生成产物经 CI/CD（CodeBuild → S3 → ECR）部署 → Amazon Bedrock AgentCore 中的 Agent Runtime 调度 Memory、Identity、Policy、Observability、Gateway 工具层与内置沙箱工具。可编辑源文件见 [`architecture.drawio`](architecture.drawio)。

## 功能
- 🎨 可视化拖拽编排 AgentCore 全部组件，点节点即弹浮层编辑；下拉切换字段联动（如 Skill 来源 inline/path/upload、Identity 入站/出站、Gateway IAM/JWT、Policy Cedar/自然语言、Runtime 代码来源 ECR/S3）
- ⚙️🚀 **Runtime 与 Harness 双中枢**：Runtime（自带编排代码，容器/制品部署）与 Harness（声明式、AgentCore 托管 Agent 循环，不可变版本 + 命名 endpoint 即时回滚）二选一，按需切换
- 🧩 **多 Agent 编排**：从云端拉取已发布 agent，一键生成编排器 Agent —— Supervisor（主控把子 Agent 包成工具按需调用）或 A2A（经 `InvokeAgentRuntime` 透传 JSON-RPC `message/send` 与对等 Agent 协作，A2A 模式只列以 `--protocol A2A` 部署的 agent）；画布自动画出主↔子 Agent 关系
- 📥 **导入已有 Agent 继续编辑**：发布时把整张画布配置存档到 S3 state 桶（`specs/<name>.json`）；导入时拉取云端 agent 列表并交叉标注「可导入」，点一下读回配置**重建可编辑画布**、改完重新发布。仅对 Studio 发布过的 agent 有效（其余 agent 逻辑封装在容器内，控制面无法还原）
- 📦 **一键场景模板**：极简对话 / 客服（带工具）/ 数据分析 / 全家桶，秒级铺满画布看效果
- 🔗 关系准确的连线（Runtime 为中枢，MCP/Skill 挂在 Gateway 下）
- 📄 实时生成 `agentcore_entry.py` / `deploy.sh` / `iam-policy.json` / `requirements.txt` / `registry.json`
- 📚 Registry 实时登记所有组件、内置工具、MCP/Skill
- 🎮 Playground 对话：**本地直连 Bedrock `converse` 真实模型回复**（有凭证即真实，否则降级模拟）/ AWS 云端两种来源；**改 System Prompt 即时生效**——系统提示随每次对话传入 Agent，调一句 prompt 立刻看到新效果，无需重新部署
- 🚀 **发布管线 trace**：发布到云端时展示组件发布路径，逐个点亮（pending→进行中→✓），全部就绪后「全部发布完成」；后台任务 + 轮询进度（不受流式超时影响），实时日志 + 部署计时心跳
- ⚡ **增量发布（三态）**：每个组件按指纹判定——制品/代码变更→全量重建；仅控制面配置变更（协议/超时/环境变量/描述等）→ `update-agent-runtime` 秒级更新（复用现有制品、不重建、保留 ARN）；未变化→跳过。Identity / MCP Target / Policy / Memory / Gateway 均支持原地快速更新
- ✅ 智能校验：未配置完整的组件自动**跳过不发布**（Runtime 未配置才阻止），状态栏显示「已配置/总数」
- ☁️ **一键发布到云端**：未本地发布会自动先发布，再真实部署到 AWS Bedrock AgentCore（原地更新，重建期间旧版本继续服务）并切到 Playground 看实时进度；自动探测云端已就绪 Agent 作为演示「托底」

> 细节：模型 ID 按区域自动加跨区域推理配置前缀（`us.`/`eu.`/`apac.`）；默认区域 `us-west-2`、默认模型 Claude Sonnet 4.5；切换部署区域时自动清理跨区残留的 toolkit 本地状态。

## 本地运行
```bash
python3 server.py            # 打开 http://127.0.0.1:8799
# 自定义端口 / 启用访问密码：
PORT=9000 STUDIO_PASSWORD=yourpass python3 server.py
```
> 后端会执行生成的代码并调用 `agentcore` CLI，默认仅绑定 `127.0.0.1`，请勿在无鉴权情况下暴露公网。

## 文件
| 文件 | 说明 |
|---|---|
| `index.html` | 单文件前端（字体内联，可离线） |
| `server.py` | 零依赖后端（发布 / Playground / 部署 / 云端调用） |
| `Dockerfile` | 容器镜像（内置 agentcore CLI + AWS CLI + zip）— 可选，用于打包到任意容器平台 |
