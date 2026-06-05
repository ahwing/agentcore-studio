# AgentCore Studio

> 拖拽编排 · 一键上线你的 AI Agent ｜ From canvas to cloud in minutes

**AgentCore Studio** 是面向 Amazon Bedrock AgentCore 的可视化编排工作台。在画布上拖拽 Runtime、Memory、Gateway、Identity、Observability、Policy 六大核心组件，以及 Code Interpreter、Browser 内置工具和挂载在 Gateway 下的 MCP 工具 / Skill，像搭积木一样组装一个 AI Agent。每次配置都会**实时生成真实可部署的产物**（入口代码、部署脚本、IAM 策略、组件注册表），并在 Registry 中即时登记。配置完成后**一键发布到云端**真实部署到 AWS，再在内置 **Playground** 里与 Agent 直接对话验证：本地接真实 Bedrock 秒级反馈、云端运行真实可信。

## 功能
- 🎨 可视化拖拽编排 AgentCore 全部组件，点节点即弹浮层编辑；下拉切换字段联动（如 Skill 来源 inline/path/upload、Identity 入站/出站、Gateway IAM/JWT、Policy Cedar/自然语言、Runtime 代码来源 ECR/S3）
- 📦 **一键场景模板**：极简对话 / 客服（带工具）/ 数据分析 / 全家桶，秒级铺满画布看效果
- 🔗 关系准确的连线（Runtime 为中枢，MCP/Skill 挂在 Gateway 下）
- 📄 实时生成 `agentcore_entry.py` / `deploy.sh` / `iam-policy.json` / `requirements.txt` / `registry.json`
- 📚 Registry 实时登记所有组件、内置工具、MCP/Skill
- 🎮 Playground 对话：**本地直连 Bedrock `converse` 真实模型回复**（有凭证即真实，否则降级模拟）/ AWS 云端两种来源
- 🚀 **发布管线 trace**：发布到云端时展示组件发布路径，逐个点亮（pending→进行中→✓），全部就绪后「全部发布完成」；实时流式日志 + 部署计时心跳
- ✅ 智能校验：未配置完整的组件自动**跳过不发布**（Runtime 未配置才阻止），状态栏显示「已配置/总数」
- ☁️ 一键真实部署到 AWS Bedrock AgentCore（原地更新，重建期间旧版本继续服务）；自动探测云端已就绪 Agent 作为演示「托底」

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

## 安全
- 源码不含任何密钥；AWS 账号、密码均为运行时动态获取 / 生成。
- 运行时生成的 `workspace/`（含 `.bedrock_agentcore.yaml`、账号信息）已在 `.gitignore` 中排除。
- 后端会执行生成代码且持有 AWS 权限，公网部署务必启用 `STUDIO_PASSWORD` 鉴权。
