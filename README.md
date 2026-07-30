# GLM Agent — 生产级 AI 微服务

基于 **智谱 AI GLM-4-Flash** 的通用 AI Agent 微服务，支持流式对话、工具调用、对话历史管理，附带 PWA 移动端界面。

## 特性

- 🧠 **GLM-4-Flash 驱动** — 智谱 AI 快速推理模型
- 🔄 **流式 SSE 输出** — 实时逐字显示，体验流畅
- 🛠️ **工具调用 (Function Calling)** — Agent 可调用外部工具
- 💾 **对话持久化** — SQLite 存储，对话历史不丢失
- 📱 **PWA 移动端** — 响应式界面，可安装到手机桌面
- 🔐 **API Key 认证** — 保护服务安全
- ⏱️ **IP 限流** — 令牌桶算法防止滥用
- 🐳 **Docker 部署** — 一键启动，随处运行
- 📊 **结构化日志** — loguru，带请求追踪
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

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/health/ready` | 就绪探测 |
| `POST` | `/chat` | 非流式聊天 |
| `POST` | `/chat/stream` | SSE 流式聊天 |
| `POST` | `/conversations` | 创建对话 |
| `GET` | `/conversations` | 对话列表 |
| `GET` | `/conversations/{id}` | 对话详情 |
| `DELETE` | `/conversations/{id}` | 删除对话 |

## 示例请求

```bash
# 非流式
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"你好，请用Python写一个快速排序"}]}'

# 流式
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"讲一个笑话"}],"stream":true}'

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
├── main.py                 # 应用入口
├── agent/
│   ├── config.py           # 配置管理 (pydantic-settings)
│   ├── models.py           # 数据模型 (Pydantic)
│   ├── chat.py             # 聊天引擎 + 工具调用循环
│   ├── store.py            # SQLite 持久化
│   ├── middleware.py        # 请求ID/计时/认证/限流
│   └── exceptions.py       # 异常体系
├── routers/
│   ├── chat.py             # 聊天路由 (/chat)
│   ├── conversations.py    # 对话管理路由
│   └── health.py           # 健康检查路由
├── static/
│   ├── index.html          # PWA Web UI
│   ├── manifest.json       # PWA 清单
│   ├── sw.js               # Service Worker
│   └── icon-*.png          # 应用图标
├── scripts/
│   └── generate_icons.py   # 图标生成脚本
├── tests/                  # 测试
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ZHIPUAI_API_KEY` | (必填) | 智谱 AI API Key |
| `ZHIPUAI_MODEL` | `glm-4-flash` | 模型名称 |
| `SERVICE_API_KEY` | (空=不启用) | 服务级认证密钥 |
| `RATE_LIMIT_PER_MINUTE` | `60` | 每 IP 每分钟限制 |
| `CORS_ORIGINS` | `*` | 允许的来源 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

## 许可证

MIT
