# AgentCore Studio

> 拖拽编排 · 一键上线你的 AI Agent ｜ From canvas to cloud in minutes
>
> 🌐 [English](README.en.md) ｜ 中文

**AgentCore Studio** 是面向 Amazon Bedrock AgentCore 的可视化编排工作台。在画布上拖拽 Runtime / Harness、Memory、Gateway、Identity、Observability、Policy 等核心组件，以及 Code Interpreter、Browser 内置工具和挂载在 Gateway 下的 MCP 工具 / Skill，像搭积木一样组装一个 AI Agent。每次配置都会**实时生成真实可部署的产物**（入口代码、部署脚本、IAM 策略、组件注册表），并在 Registry 中即时登记。配置完成后**一键发布到云端**真实部署到 AWS，再在内置 **Playground** 里与 Agent 直接对话验证：本地接真实 Bedrock 秒级反馈、云端运行真实可信。

![AgentCore Studio 界面](ui.png)

## 架构

![AgentCore Studio 架构图](architecture.png)

> 开发者通过 Studio（可部署在 App Runner / EC2 / ECS / EKS / 本地）拖拽编排 → 生成产物经 CI/CD（CodeBuild → S3 → ECR）部署 → Amazon Bedrock AgentCore 中的 Agent Runtime（平台 V1 / V2，microVM / instances）调度 Memory（含自管理策略）、Identity、Payments（预览）、Policy、Observability / Evaluations（含自建评估器）、Gateway 工具层（含拦截器）与内置沙箱工具；部署走 AgentCore CLI v1。可编辑源文件见 [`architecture.drawio`](architecture.drawio)。

## 功能

### 🎨 可视化编排
- 拖拽编排 AgentCore 全部组件，点节点即弹浮层编辑；下拉切换字段联动（如 Skill 来源 inline/path/upload、Identity 入站/出站、Gateway IAM/JWT、Policy Cedar/自然语言、Runtime 代码来源 ECR/S3）
- ⚙️🚀 **Runtime 与 Harness 双中枢**：Runtime（自带编排代码，容器/制品部署）与 Harness（声明式、AgentCore 托管 Agent 循环，不可变版本 + 命名 endpoint 即时回滚）二选一，按需切换
- 🧬 **Runtime 平台版本 V1/V2 + 计算类型**：Runtime 节点可选 V1（默认，秒级 READY）或 V2（快照启动，冷启动稳定）；选 V2 后区域只列 5 个支持区、环境变量上限收紧到 1.5KB/2.5KB 并实时显示用量、pre-flight 提示「更新要几分钟 / 120 秒内 /ping 健康」、部署脚本经 `update-agent-runtime --platform-version` 下发并轮询到 READY；计算类型 instances（容量提供方，会话最长 14 天）把超时上限放到 1209600 秒
- ✨ **AI 生成画布（NL→Canvas）**：一句话描述你想要的 Agent，自动生成节点与连线的**可编辑画布**，生成后继续拖拽微调并自动 pre-flight 校验
- 🧠 **深度生成（Deep Generate）**：4 步智能编排（需求分解 → 组件配置 → System Prompt → 校验），SSE 流式实时进度反馈，自动生成完整可部署产物 + 选型决策理由 + 部署前报告；生成结果一键应用到画布
- ⏰ **定时触发（EventBridge Scheduler）**：需求中包含周期性执行时自动引入，部署脚本生成 `aws scheduler create-schedule` + IAM Role，支持 cron/rate 表达式
- 📦 **一键场景模板**：极简对话 / 客服（带工具）/ 数据分析 / 全家桶 / ⚠ 典型踩坑，秒级铺满画布
- 🔗 关系准确的连线（Runtime 为中枢，MCP/Skill 挂在 Gateway 下）

### 🎮 Playground：本地秒级验证 → 迭代闭环
- **本地直连 Bedrock `converse` 真实模型回复** / AWS 云端两种来源；来源状态**诚实标注**：本地·真跑（执行你编排的工具）/ 本地·模型（直连模型未跑工具）/ 本地模拟 / AWS 云端
- **改 System Prompt 即时生效**——系统提示随每次对话传入 Agent，调一句 prompt 立刻看到新效果，无需重新部署
- 🔍 **调用透视（Trace）**：每条回复展开看工具调用（入参/结果）、token 用量、延迟、模型——本地与云端共用一处数据源
- ⚖️ **A/B 对比**：同一句输入，基线 vs 候选 System Prompt 并排跑，直接判断改动变好还是变差
- 📋 **测试集**：保存一组输入一键全跑，结果**与上次对比标注变化**（新/变化/未变），轻量回归
- 🔬 **组件消融 + 断言**：选一个组件关掉，用「没它就做不到」的预置探针 + 可自动判定的断言（期望调用某工具 / 期望输出精确值），A（含）与 B（去掉）各自**真实重新发布产物并调用一次**，并排给出 `断言证明 / 并非必需 / 探针未命中 / 行为差异 / 产物差异` 分级判定。消融 Gateway 会连带去掉挂在它下面的组件；若某组件不进 Agent 代码（如 Memory）或本地可调用工具集不变（如 web_search 类云端 target），直接判 `本地不可判定` 并跳过调用，不产出误导性的"没区别"
- 📄 **演示证据留档**：一键导出 Markdown——画布组件与关键配置、pre-flight 结论、逐轮交互（工具入参出参 / token / 延迟）、断言结果、产物差异、五份产物全文、口径说明。带走的是可转给客户的文件，不是记忆
- 💾 **对话历史持久化**：各 Agent 的对话与历史落地本地，刷新不丢

### 📄 实时产物 & 发布
- 实时生成 `agentcore_entry.py` / `deploy.sh` / `iam-policy.json` / `requirements.txt` / `registry.json`；Registry 实时登记所有组件、内置工具、MCP/Skill
- ⚡ **产物 diff 直播**：改一个配置，产物面板立刻列出**同时变化的所有文件**与语义摘要（新增工具函数 / IAM 语句与权限 / 角色内联策略 / 部署步骤 / 依赖），当前文件内新增行绿色高亮。一个功能节点 = 工具代码 + 对应最小 IAM 权限 + 部署步骤 + 注册记录，四处一起长出来（例：开一个 Observability → `deploy.sh` +1 步骤、`iam-policy.json` +5 行含 `logs:*`/`xray:*`、`registry.json` +2、`requirements.txt` +1）
- ✅ **Pre-flight 校验**：除完整性检查外，做**跨节点语义/区域/安全**校验（Runtime V2 选了不支持的区、web_search 不支持的区、知识库跨区、Policy ENFORCE 无 permit 会全锁、出公网风险等），设计期状态条实时显示「风险」并在部署前拦截提示
- 🛡️ **风险面板 + 一键修复**：点状态条展开每条风险，支持「🎯 定位节点」跳到出问题的组件，以及针对性修复（改区域 / 对齐知识库区域 / 插入 permit 语句 / 网络改回 SANDBOX）；「全部修复」按迭代收敛（修一条→重算，因为一条修复会改变其他条的判定）。配合 ⚠ 典型踩坑场景，一次触发四类风险
- 🚀 **发布管线 trace**：发布时展示组件发布路径，逐个点亮（pending→进行中→✓）；后台任务 + 轮询进度（不受流式超时影响），实时日志 + 部署计时心跳
- ⚡ **增量发布（三态）**：按指纹判定——制品/代码变更→全量重建；仅控制面配置变更（协议/超时/环境变量/描述等）→ `update-agent-runtime` 秒级更新（复用制品、保留 ARN）；未变化→跳过。Identity / MCP Target / Policy / Memory / Gateway 均支持原地快速更新
- 🧬 **发布指纹对比表**：发布前预演走哪条路径。逐项列出制品指纹（entry 代码 / 区域 / 部署方式 / 模型 / 框架 / Memory / Observability / 内置工具 / Skills）与配置指纹（协议 / 超时 / 环境变量 / 描述 / System Prompt）的**变 / 未变**，给出判定与预计耗时——只改一句 System Prompt 为什么是秒级、换个模型为什么要重建，一眼看清
- ☁️ **一键发布到云端**：未本地发布会自动先发布，再真实部署到 AWS Bedrock AgentCore（原地更新，重建期间旧版本继续服务）并切到 Playground 看实时进度；自动探测云端已就绪 Agent 作为演示「托底」

### 🧩 多 Agent & 复用
- **多 Agent 编排**：从云端拉取已发布 agent，一键生成编排器 Agent —— Supervisor（主控把子 Agent 包成工具按需调用）或 A2A（经 `InvokeAgentRuntime` 透传 JSON-RPC `message/send` 与对等 Agent 协作，A2A 模式只列以 `--protocol A2A` 部署的 agent）；画布自动画出主↔子 Agent 关系
- **导入已有 Agent 继续编辑**：发布时把整张画布配置存档到 S3 state 桶（`specs/<name>.json`）；导入时拉取云端 agent 列表并交叉标注「可导入」，点一下读回配置**重建可编辑画布**、改完重新发布。仅对 Studio 发布过的 agent 有效

> 细节：模型 ID 按区域自动加跨区域推理配置前缀（`us.`/`eu.`/`apac.`）；默认区域 `us-west-2`、默认模型 Claude Sonnet 5.5（另有 Opus 5.5、Haiku 5.5、GPT 6.1 / 6；新一代模型不传 temperature）；切换部署区域时自动清理跨区残留的 toolkit 本地状态。
>
> Memory 长期记忆策略支持 `SEMANTIC / SUMMARY / USER_PREFERENCE / EPISODIC / CUSTOM`（对应 API 的 `*MemoryStrategy`）；`STM` 模式只保留事件流不建策略，含 `LTM` 时经 `update-memory --memory-strategies` 原地追加。Policy 的 enforcement mode（`LOG_ONLY` / `ENFORCE`）通过 Gateway 的 `policyEngineConfiguration` 生效，不是策略引擎自身的参数。
>
> `Evaluations` 选内置指标族（quality / tool_use / trajectory / safety / all，来自 `agentcore eval evaluator list` 的内置 evaluator；也可在「追加 evaluator ID」里填自定义 LLM 裁判 / Lambda 代码评估器），发布时经 `agentcore eval online create` 按采样率挂到指定 endpoint 做持续在线评估；`Optimization` 的配置包经 `create-configuration-bundle` 把 System Prompt / 模型 / 采样参数存成不可变版本快照（components 是 `{组件 ARN: {configuration: 自由 JSON}}`）。`Observability` 的日志级别 / 链路开关 / 采样率落成 OpenTelemetry SDK 标准环境变量（`OTEL_LOG_LEVEL` / `OTEL_TRACES_EXPORTER` / `OTEL_TRACES_SAMPLER`），仪表盘开关经 `cloudwatch put-dashboard` 建 4 个 widget（调用量 / 错误 / p50-p95 延迟 / token / 错误日志）。

## 功能截图

<table>
<tr>
<td width="50%"><img src="docs/screenshots/01-canvas.png" alt="画布铺开 13 个组件"><br><sub>画布铺开 13 个组件：Runtime 中枢，Gateway 是工具入口</sub></td>
<td width="50%"><img src="docs/screenshots/02-node-config.png" alt="点开组件看配置"><br><sub>点开任一组件，看它真实可配的字段</sub></td>
</tr>
<tr>
<td><img src="docs/screenshots/03-preflight.png" alt="Pre-flight 风险面板"><br><sub>Pre-flight：部署前校验跨节点风险，可定位节点并一键修复</sub></td>
<td><img src="docs/screenshots/04-artifacts.png" alt="实时产物"><br><sub>实时生成真实可部署产物：入口代码 / 部署脚本 / IAM / 注册表</sub></td>
</tr>
<tr>
<td><img src="docs/screenshots/05-artifact-diff.png" alt="产物 diff 直播"><br><sub>改一个配置，四个产物文件同时联动变化</sub></td>
<td><img src="docs/screenshots/06-fingerprint.png" alt="发布指纹对比"><br><sub>指纹判定：只改 System Prompt → 秒级更新，不重建</sub></td>
</tr>
<tr>
<td><img src="docs/screenshots/07-playground.png" alt="Playground"><br><sub>Playground：不部署就对话验证，来源状态诚实标注</sub></td>
<td><img src="docs/screenshots/08-registry.png" alt="Registry"><br><sub>所有组件、内置工具、MCP/Skill 在 Registry 实时登记</sub></td>
</tr>
</table>

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
| `server.py` | 零依赖后端（发布 / Playground / 部署 / 云端调用 / NL→Canvas / 深度生成中继） |
| `deep_generate.py` | 深度生成引擎（4 步 LLM 编排 + 并行优化 + SSE 流式进度） |
| `Dockerfile` | 容器镜像（内置 agentcore CLI + AWS CLI + zip）— 可选，用于打包到任意容器平台 |



## 演示材料

用于分享的演示稿，均按"功能 → 使用场景 → 价值"组织，正文之后附 8 张真实界面截图：

| 文件 | 面向 | 说明 |
|---|---|---|
| `AgentCore-Studio_客户方案介绍_20260729.pptx` | 客户 | 价值旅程：从想法到上云、安全合规内建、成本与落地路径 |
| `AgentCore-Studio_内部技术分享_SA_30min_20260729.pptx` | 内部 SA | 客户旅程四段 + 一页 AgentCore 机制速览（内部使用） |

> 内部 SA 版含面向 SA 的定位话术，仅供内部分享。截图源文件见 `docs/screenshots/`。
