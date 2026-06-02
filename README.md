# AgentCore Studio

> 拖拽编排 · 一键上线你的 AI Agent ｜ From canvas to cloud in minutes

**AgentCore Studio** 是面向 Amazon Bedrock AgentCore 的可视化编排工作台。在画布上拖拽 Runtime、Memory、Gateway、Identity、Observability、Policy 六大核心组件，以及 Code Interpreter、Browser 内置工具和挂载在 Gateway 下的 MCP 工具 / Skill，像搭积木一样组装一个 AI Agent。每次配置都会**实时生成真实可部署的产物**（入口代码、部署脚本、IAM 策略、组件注册表），并在 Registry 中即时登记。配置完成后**一键发布到云端**真实部署到 AWS，再在内置 **Playground** 里与 Agent 直接对话验证：本地模拟秒级反馈、云端运行真实可信。

## 功能
- 🎨 可视化拖拽编排 AgentCore 全部组件，点节点即弹浮层编辑
- 🔗 关系准确的连线（Runtime 为中枢，MCP/Skill 挂在 Gateway 下）
- 📄 实时生成 `agentcore_entry.py` / `deploy.sh` / `iam-policy.json` / `requirements.txt` / `registry.json`
- 📚 Registry 实时登记所有组件、内置工具、MCP/Skill
- 🚀 本地发布 + 🎮 Playground 对话（本地模拟 / AWS 云端两种来源）
- ☁️ 一键真实部署到 AWS Bedrock AgentCore

## 本地运行
```bash
python3 server.py            # 打开 http://127.0.0.1:8799
# 自定义端口 / 启用访问密码：
PORT=9000 STUDIO_PASSWORD=yourpass python3 server.py
```
> 后端会执行生成的代码并调用 `agentcore` CLI，默认仅绑定 `127.0.0.1`，请勿在无鉴权情况下暴露公网。

## 部署到 AWS App Runner（公网 + Basic Auth）
需 Docker、AWS CLI 凭证、`agentcore` 工具链。
```bash
bash apprunner-deploy.sh     # 构建镜像→ECR→IAM 角色→App Runner，输出 URL 与随机密码
```
说明见脚本内注释。实例 IAM 角色权限较广（用于真实部署），建议放独立账号并在演示后销毁。

## 文件
| 文件 | 说明 |
|---|---|
| `index.html` | 单文件前端（字体内联，可离线） |
| `server.py` | 零依赖后端（发布 / Playground / 部署 / 云端调用） |
| `Dockerfile` | 容器镜像（内置 agentcore CLI + zip） |
| `apprunner-deploy.sh` | 一键部署到 App Runner |

## 安全
- 源码不含任何密钥；AWS 账号、密码均为运行时动态获取 / 生成。
- 运行时生成的 `workspace/`（含 `.bedrock_agentcore.yaml`、账号信息）已在 `.gitignore` 中排除。
- 后端会执行生成代码且持有 AWS 权限，公网部署务必启用 `STUDIO_PASSWORD` 鉴权。
