# GLM Agent — 生产级 AI 微服务

基于 **智谱 AI GLM-4-Flash** 的通用 AI Agent 微服务，支持流式对话、工具调用、对话历史管理，附带 PWA 移动端界面。

## 特性

- 🧠 **GLM-4-Flash 驱动** — 智谱 AI 快速推理模型
- 🔄 **流式 SSE 输出** — 实时逐字显示，体验流畅
- 🛠️ **工具调用 (Function Calling)** — Agent 可调用外部工具
- 💾 **对话持久化** — SQLite 存储，对话历史不丢失
- 📱 **PWA 移动端** — 响应式界面，可安装到手机桌面
- 🔐 **双通道认证** — 服务级 API Key（X-API-Key）+ 用户级 JWT（登录），纵深防御
- 👤 **用户系统** — 注册/登录/密码加密（bcrypt）/登录记录，对话历史按账号隔离同步
- 🚶 **游客模式** — 免登录即可试用聊天（限流保护），登录后自动同步历史
- ⏱️ **IP 限流** — 令牌桶算法防止滥用，Auth 端点独立 5 次/分钟防爆破
- 🐳 **Docker 部署** — 一键启动，随处运行
- 📊 **结构化日志** — loguru，带请求追踪
- 🧠 **自我迭代** — 从对话中学习用户偏好，个性化提示词（persona）
- 🔌 **可扩展** — 预留 OpenAI 兼容接口

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 ZHIPUAI_API_KEY
```

### 3. 启动服务

```bash
python main.py
# 或
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 打开界面

- **Web UI**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

## Docker 部署

```bash
# 配置环境变量
export ZHIPUAI_API_KEY=your-key

# 启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止
docker-compose down
```

## API 端点

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `GET` | `/health` | 健康检查 | 公开 |
| `GET` | `/health/ready` | 就绪探测 | 公开 |
| `POST` | `/auth/register` | 注册 | 公开（限流） |
| `POST` | `/auth/login` | 登录 | 公开（限流） |
| `GET` | `/auth/me` | 当前用户信息 | JWT |
| `GET` | `/auth/login-history` | 登录记录 | JWT |
| `POST` | `/chat` | 非流式聊天 | 公开（游客） |
| `POST` | `/chat/stream` | SSE 流式聊天 | 公开（游客） |
| `POST` | `/conversations` | 创建对话 | JWT / API Key |
| `GET` | `/conversations` | 对话列表 | JWT / API Key |
| `GET` | `/conversations/{id}` | 对话详情 | JWT / API Key |
| `DELETE` | `/conversations/{id}` | 删除对话 | JWT / API Key |
| `POST` | `/iteration/feedback` | 提交反馈 | JWT |
| `GET` | `/iteration/feedback` | 反馈统计 | JWT |
| `GET` | `/iteration/memory` | 获取记忆 | JWT |
| `POST` | `/iteration/memory` | 主动记忆 | JWT |
| `DELETE` | `/iteration/memory/{key}` | 删除记忆 | JWT |
| `GET` | `/iteration/persona` | 个性化提示词 | JWT |

> **认证说明**：服务启用 `SERVICE_API_KEY` 后，受保护端点接受两种凭据——
> `X-API-Key: <service_api_key>`（服务间调用）或 `Authorization: Bearer <JWT>`（登录用户）。
> `/chat` 与 `/auth/*` 始终公开，保障游客试用与注册登录。

## 示例请求

```bash
# 游客聊天（免登录，限流保护）
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"讲一个笑话"}],"stream":true}'

# 注册并登录
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"Secret123","nickname":"爱丽丝"}'
# → 返回 data.token，即为 JWT

# 登录获取 Token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"Secret123"}' | python -c "import sys,json;print(json.load(sys.stdin)['data']['token'])")

# 登录用户聊天（对话持久化到账号）
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"messages":[{"role":"user","content":"你好，请用Python写一个快速排序"}],"stream":true}'

# 查看对话历史（需 JWT）
curl http://localhost:8000/conversations \
  -H "Authorization: Bearer $TOKEN"

# 服务间调用（X-API-Key）
curl http://localhost:8000/conversations \
  -H "X-API-Key: $SERVICE_API_KEY"

# 带工具调用
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages":[{"role":"user","content":"北京今天天气怎么样？"}],
    "tools":[{
      "type":"function",
      "function":{
        "name":"get_weather",
        "description":"获取指定城市的天气",
        "parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}
      }
    }]
  }'
```

## 手机端使用

1. 启动服务后，用手机浏览器访问 `http://<你的IP>:8000`
2. **iOS Safari**: 点击分享按钮 → "添加到主屏幕"
3. **Android Chrome**: 点击菜单 → "添加到主屏幕"
4. 安装后像原生 App 一样使用，支持离线缓存

## 项目结构

```
glm-agent/
├── main.py                 # 应用入口（中间件链 + 路由注册 + 生命周期）
├── agent/
│   ├── config.py           # 配置管理 (pydantic-settings)
│   ├── models.py           # 数据模型 (Pydantic)
│   ├── chat.py             # 聊天引擎 + 工具调用循环
│   ├── store.py            # SQLite 持久化
│   ├── middleware.py        # 请求ID/计时/双通道认证/限流/CSP
│   ├── users.py            # 用户系统（注册/登录/JWT/bcrypt/登录记录）
│   ├── iteration.py        # 自我迭代（反馈/记忆/persona 生成）
│   └── exceptions.py       # 异常体系
├── routers/
│   ├── auth.py             # 认证路由 (/auth/*)
│   ├── chat.py             # 聊天路由 (/chat)
│   ├── conversations.py    # 对话管理路由
│   ├── iteration.py        # 自我迭代路由 (/iteration/*)
│   └── health.py           # 健康检查路由
├── static/
│   ├── index.html          # PWA Web UI（含登录/注册界面）
│   ├── css/app.css         # 样式（亮/暗双模式 + 认证弹窗）
│   ├── js/app.js           # 前端逻辑（SSE 流式 + 认证 + 历史同步）
│   ├── manifest.json       # PWA 清单
│   ├── sw.js               # Service Worker
│   └── icon-*.png          # 应用图标
├── scripts/
│   └── generate_icons.py   # 图标生成脚本
├── tests/                  # 测试（健康检查 + 认证访问控制）
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ZHIPUAI_API_KEY` | (必填) | 智谱 AI API Key |
| `ZHIPUAI_MODEL` | `glm-4-flash` | 模型名称 |
| `SERVICE_API_KEY` | (空=不启用) | 服务级认证密钥；**启用后**受保护端点需 X-API-Key 或 JWT |
| `JWT_SECRET` | (自动生成) | JWT 签名密钥；建议生产环境显式配置强随机值 |
| `RATE_LIMIT_PER_MINUTE` | `60` | 每 IP 每分钟限制（0 不限制） |
| `CORS_ORIGINS` | `*` | 允许的来源 |
| `DATABASE_PATH` | `data/conversations.db` | SQLite 数据库路径 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `MAX_TOOL_ROUNDS` | `10` | 工具调用最大轮次（防死循环） |

## 许可证

MIT
