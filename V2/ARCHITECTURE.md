# V2 架构与API接口文档

## 一、系统架构

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端应用                              │
│              (frontend/ 或第三方调用方)                      │
└─────────────────────────────────────────────────────────────┘
                              │ HTTP/REST API
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     V2 Web 服务层                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Flask App (app.py) - 端口: 5002                     │   │
│  │ - 会话隔离管理                                       │   │
│  │ - 路由蓝图注册                                       │   │
│  │ - 认证中间件                                         │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Routes 路由层                                        │   │
│  │ - test_routes.py    测试执行                         │   │
│  │ - question_routes.py 问题生成                        │   │
│  │ - chat_routes.py    对话交互                         │   │
│  │ - file_routes.py    文件管理                         │   │
│  │ - report_routes.py  报告查看                         │   │
│  │ - persona_routes.py 用户画像                         │   │
│  │ - product_routes.py 商品库                           │   │
│  │ - site_routes.py    多网站管理                       │   │
│  │ - task_routes.py    任务队列                         │   │
│  │ - check_routes.py   健康检查                         │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Services 服务层                                      │   │
│  │ - session_service.py  会话状态管理                   │   │
│  │ - test_executor.py    测试执行器                     │   │
│  │ - knowledge_service.py 知识库服务                    │   │
│  │ - process_manager.py  进程管理                       │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    MCP_Server 核心层                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ tools_api.py - 统一工具接口                          │   │
│  │ - run_debug_test()      单网站测试                   │   │
│  │ - run_concurrent_test() 并发测试                     │   │
│  │ - generate_questions_concurrent() 问题生成           │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ config.py - 统一配置管理                             │   │
│  │ - LLM_API_KEY/BASE_URL/MODEL_NAME                   │   │
│  │ - 多模型配置回退机制                                 │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 PlayWright 自动化测试层                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ solo_worker_PlayWright/ - 单网站测试                 │   │
│  │ - main.py              测试入口                      │   │
│  │ - test.py              测试逻辑                      │   │
│  │ - reports/             测试报告                      │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ max_worker/ - 并发测试                               │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 评估模块                                             │   │
│  │ - judge.py              裁判评估                     │   │
│  │ - chaos_matrix.py       混沌矩阵                     │   │
│  │ - human_like_eval.py    拟人化评估                   │   │
│  │ - report.py             报告生成                     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 目录结构

```
V2/
├── web/                          # Flask Web服务
│   ├── app.py                    # 应用入口
│   ├── config.py                 # Web配置
│   ├── database.py               # 数据库操作
│   ├── agent_wrapper.py          # Agent适配器
│   ├── routes/                   # 路由模块
│   │   ├── test_routes.py        # 测试执行
│   │   ├── question_routes.py    # 问题生成
│   │   ├── chat_routes.py        # 对话交互
│   │   ├── file_routes.py        # 文件管理
│   │   ├── report_routes.py      # 报告管理
│   │   ├── persona_routes.py     # 用户画像
│   │   ├── product_routes.py     # 商品库
│   │   ├── site_routes.py        # 多网站
│   │   ├── task_routes.py        # 任务队列
│   │   └── check_routes.py       # 健康检查
│   ├── services/                 # 服务层
│   │   ├── session_service.py    # 会话管理
│   │   ├── test_executor.py      # 测试执行器
│   │   ├── knowledge_service.py  # 知识库服务
│   │   └── process_manager.py    # 进程管理
│   ├── middleware/               # 中间件
│   └── templates/                # 模板
├── MCP_Server/                   # 核心业务层
│   ├── config.py                 # 统一配置
│   ├── tools_api.py              # 工具接口
│   ├── mcp_server.py             # MCP协议服务
│   ├── types.py                  # 类型定义
│   └── lib/PlayWright/           # PlayWright自动化
│       ├── solo_worker_PlayWright/  # 单网站测试
│       ├── max_worker/              # 并发测试
│       ├── judge.py                 # 裁判评估
│       ├── chaos_matrix.py          # 混沌矩阵
│       ├── human_like_eval.py       # 拟人化评估
│       └── report.py                # 报告生成
├── data/                         # 数据目录
│   ├── logs/                     # 日志文件
│   └── tasks.db                  # 任务数据库
├── Dockerfile                    # Docker构建
├── docker-compose.yml            # 容器编排
├── start.sh                      # 启动脚本
└── requirements.txt              # Python依赖
```

---

## 二、API接口文档

### 2.1 基础信息

- **Base URL**: `http://localhost:5002/api`
- **认证方式**: 可选API Token（设置 `API_AUTH_TOKEN` 环境变量）
- **数据格式**: JSON
- **字符编码**: UTF-8

---

### 2.2 测试执行 API

#### POST /api/run_test
运行单网站测试

**请求体**:
```json
{
  "session_id": "string",      // 会话ID（可选）
  "url": "string",             // 测试网站URL
  "questions": ["string"],     // 测试问题列表
  "username": "string",        // 登录用户名（可选）
  "password": "string"         // 登录密码（可选）
}
```

**响应**:
```json
{
  "success": true,
  "message": "测试已启动"
}
```

#### POST /api/run_concurrent_test
运行并发测试

**请求体**:
```json
{
  "session_id": "string",
  "target_sites": [1, 2, 3],   // 目标网站ID列表
  "worker_count": 3,           // 并发数
  "question_count": 10         // 每站点问题数
}
```

#### GET /api/test/status
获取测试状态

**参数**: `session_id` (query)

**响应**:
```json
{
  "success": true,
  "is_running": false,
  "progress": 100,
  "results": [...]
}
```

#### POST /api/test/stop
停止测试

**请求体**:
```json
{
  "session_id": "string"
}
```

---

### 2.3 问题生成 API

#### POST /api/questions/generate
生成测试问题

**请求体**:
```json
{
  "content": "string",         // 知识库内容
  "count": 10,                 // 生成数量
  "multi_turn": 1,             // 多轮对话轮数（1=单轮）
  "session_id": "string",      // 会话ID
  "product_content": "string"  // 商品库内容（可选）
}
```

**响应**:
```json
{
  "success": true,
  "questions": [
    {"question": "string", "question_type": "normal", "group_index": 0}
  ],
  "count": 10
}
```

#### POST /api/questions/generate-persona
生成用户画像问题

**请求体**:
```json
{
  "persona_id": "string",
  "count": 5,
  "session_id": "string"
}
```

#### GET /api/questions
获取已生成的问题

**参数**: `session_id`, `target` (query)

---

### 2.4 文件管理 API

#### GET /api/files
获取上传文件列表

**响应**:
```json
{
  "success": true,
  "files": [
    {"name": "doc.docx", "size": 1024, "modified": "2026-01-01"}
  ]
}
```

#### POST /api/upload
上传文件

**请求**: `multipart/form-data`
- `file`: 文件内容
- `session_id`: 会话ID（可选）

**支持格式**: `.txt`, `.md`, `.docx`, `.xlsx`, `.pdf`

**响应**:
```json
{
  "success": true,
  "filename": "document.docx",
  "size": 1024
}
```

#### DELETE /api/files/{filename}
删除文件

---

### 2.5 对话交互 API

#### POST /api/chat
对话式交互

**请求体**:
```json
{
  "message": "string",
  "session_id": "string",
  "knowledge": ["file1.docx"],
  "url": "string",
  "username": "string",
  "password": "string",
  "bot_name": "string"
}
```

**响应**:
```json
{
  "success": true,
  "response": "string",
  "action": "questions_generated"
}
```

---

### 2.6 报告管理 API

#### GET /api/reports
获取报告列表

**参数**: `session_id` (query)

#### GET /api/reports/{report_id}
获取报告详情

#### GET /api/report/{task_id}
获取任务报告

---

### 2.7 用户画像 API

#### GET /api/personas
获取画像列表

#### GET /api/personas/{persona_id}
获取画像详情

#### POST /api/personas
创建画像

**请求体**:
```json
{
  "name": "string",
  "description": "string",
  "traits": {...}
}
```

---

### 2.8 商品库 API

#### GET /api/products
获取商品列表

#### POST /api/products/upload
上传商品数据

#### GET /api/products/search
搜索商品

---

### 2.9 多网站管理 API

#### GET /api/sites
获取网站列表

#### POST /api/sites
添加网站配置

---

### 2.10 任务队列 API

#### GET /api/tasks
获取任务列表

#### GET /api/tasks/{task_id}
获取任务详情

#### POST /api/tasks
创建任务

**请求体**:
```json
{
  "task_type": "single_test",
  "url": "string",
  "questions": [],
  "worker_count": 1
}
```

#### POST /api/tasks/{task_id}/cancel
取消任务

#### GET /api/tasks/history
获取任务历史

---

### 2.11 健康检查 API

#### GET /api/status
服务状态检查

**响应**:
```json
{
  "success": true,
  "status": "ok"
}
```

#### GET /api/mode
获取执行模式

**响应**:
```json
{
  "success": true,
  "mode": "local",
  "agent_available": true
}
```

---

## 三、配置说明

### 3.1 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `LLM_API_KEY` | LLM API密钥 | 必填 |
| `LLM_API_BASE_URL` | LLM API地址 | 必填 |
| `LLM_MODEL_NAME` | 模型名称 | qwen-plus |
| `VL_API_KEY` | 视觉模型API密钥 | 可选，回退LLM_API_KEY |
| `JUDGE_API_KEY` | 裁判模型API密钥 | 可选，回退LLM_API_KEY |
| `TEST_LOGIN_URL` | 测试网站URL | 可选 |
| `TEST_USERNAME` | 测试用户名 | 可选 |
| `TEST_PASSWORD` | 测试密码 | 可选 |
| `V2_PORT` | 服务端口 | 5002 |
| `EXECUTION_MODE` | 执行模式 | local |

### 3.2 配置优先级

```
专用配置 > LLM基础配置 > 默认值

例如裁判模型配置:
JUDGE_API_KEY → LLM_API_KEY → 报错
```

---

## 四、会话隔离机制

### 4.1 多用户支持

- 每个用户通过 `session_id` 隔离
- Agent实例按session缓存
- 测试问题、报告、日志均隔离存储

### 4.2 隔离范围

| 资源 | 隔离方式 |
|------|----------|
| Agent实例 | `_agent_pool[session_id]` |
| 会话状态 | `session_status[session_id]` |
| 日志队列 | `session_logs[session_id]` |
| 问题文件 | `questions/{session_id}/test_questions.txt` |
| 测试报告 | `reports/{session_id}/` |

### 4.3 自动清理

- 超时时间: 30分钟无活动
- 清理间隔: 每10分钟检查
- 跳过正在运行的会话

---

## 五、Docker部署

### 5.1 构建镜像

```bash
cd V2
docker build -t aiwa-v2:latest .
```

### 5.2 启动服务

```bash
docker-compose up -d
```

### 5.3 端口映射

- 5002: Web API服务

---

## 六、错误码说明

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未授权（需要API Token） |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

---

## 七、版本历史

- **v2.0.0**: 初始版本，模块化架构
- 复用原版 `Agent_Test/web` 路由结构
- 集成 `MCP_Server` 核心功能
- 支持多用户会话隔离