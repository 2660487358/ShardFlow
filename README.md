<div align="center">

# ShardFlow

**面向代码与办公场景的个人智能助手引擎**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Java](https://img.shields.io/badge/Java-21-ED8B00?logo=openjdk&logoColor=white)](https://openjdk.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-1C3C3C?logo=langchain&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## 主包关于这个项目的 idea

我们都知道在一个会话内执行任务的时候如果上下文过长 Agent 就会遗忘某个信息。

针对这个问题，AI Coding 范式 Harness Engineering 的解决办法是会话上下文生命周期管理。

但是这里的 Harness Engineering 还是开发者对于 AI Coding 的约束，在准备阶段仍然需要开发者去手动管理，对于非开发者来说有一定使用门槛。

主包在做该 Agent 的时候，就尝试将该机制内化，不需要用户去手动做上下文生命周期管理的工作而是 Agent 内部自动管理，这样就减少了一部分前置准备时间。

试想一下你正在做一个超长的重构任务，不需要做任何前置准备和任务状态管理工作，在产生上下文过长引发一系列任务的时候只需要点击一下按钮 Agent 就带着任务状态自动传递到了下一个的上下文，貌似还挺方便哈。并且我还设计了一套针对上下文传递时机的方案，保证一定是以用户的意愿为第一主旨。

但是这种方案就会产生一些问题，首先迎面而来的就是记忆管理混乱，记忆管理就像打斗地主的时候不整理手里的牌一样，非常混乱。针对这个问题，主包设计了记忆树机制，同一个任务源会被归类到一个树下，并将这个树可视化，看着貌似还挺有意思的吧。如果是思维比较发散的人用这个机制去学习，可能会真的会造出来一个树状的记忆。而且主包觉得在都在使用 AI Coding 的背景下，工作的全链路可追溯和将工作过程归纳成可复用资产变得尤为重要，记忆树机制对这些方面也同样有加持。 此外还有各种成本的产生，以及关于状态传递内容的考量等等，这也是最核心的挑战。

关于这个想法，其实还参考了 LangGraph 的 checkpointer 机制，用一个不是很恰当的比喻就是把快照的产生从节点上升到会话，从而实现会话记忆的共享。

同时主包设计了 Skills 和 MCP 的管理，感觉使用这些东西更加简便了，对不了解这方面的人更加友好。

而且这个项目也不是简单的 Python 核心推理模块的 demo ， 也是主包对工程化 Agent 的一次尝试。

觉得主包想法还行的可以点个 star，看我把这个 Agent 做到上线，觉得主包想法没啥用的也欢迎批评指正，同时也可以点个star，留下来看我笑话。

### 六层架构

ShardFlow 的 Python 推理层采用六层架构设计：

| 层级 | 职责 | 核心模块 |
|:---|:---|:---|
| L1 用户交互层 | 意图识别、实体提取、会话管理、跨端口路由 | `intent_recognizer` `session_recovery` `port_router` |
| L2 Agent 核心层 | ReAct 循环、状态包管理、策略引擎、用户画像、记忆编排 | `langgraph_engine` `context_shard` `strategy_engine` `memory_orchestrator` |
| L3 知识检索层 | 联网搜索、用户画像检索、知识库 RAG、缓存管理 | `web_searcher` `kb_pipeline` `knowledge_searcher` |
| L4 决策推理层 | 决策推理、工具择优选择、错误处理 | `decision_reasoning` `tool_selector` `error_handler` |
| L5 工具执行层 | 工具注册、MCP 执行、HTTP 执行、结果解析 | `tool_registry` `mcp_executor` `http_executor` |
| L6 安全合规层 | 输入/输出守卫、MCP 安全网关、审计日志 | `input_guard` `output_guard` `mcp_security` `audit_logger` |

---

## 技术栈

| 类别 | 技术 | 说明 |
|:---|:---|:---|
| Python 推理层 | FastAPI + LangGraph + MCP Client + LlamaIndex | 核心推理引擎，ReAct 循环与工具调用 |
| Java 外围服务 | Spring Boot 4 + MyBatis-Plus 3.5 + Sa-Token 1.45 | 认证、持久化、画像、MCP 注册中心 |
| 前端 | React 19 + TypeScript + Vite | 助手形态 UI，SSE 流式对话 |
| 关系数据库 | PostgreSQL 18 | 状态快照、策略记录、用户画像 |
| 向量检索 | Milvus 2.5 | 策略语义检索、知识库文档向量检索 |
| 缓存 | Redis 7 | 三级缓存 L1 层，Python 直读跳过 Java |
| 文档处理 | LlamaIndex | 文档解析、分块、向量化、混合检索 |
| 对象存储 | MinIO | 文件存储、知识库文档存储 |
| 运行环境 | Java 21 + Python 3.11+ | Java 21 LTS 虚拟线程支持 |

---

## 项目结构

```
ShardFlow/
├── shardflow-agent/          # Python 推理层（FastAPI）
│   └── app/layers/            # 六层架构模块
│       ├── interaction/      # L1 用户交互层
│       ├── agent_core/        # L2 Agent 核心层
│       ├── retrieval/         # L3 知识检索层
│       ├── reasoning/         # L4 决策推理层
│       ├── tool/              # L5 工具执行层
│       └── security/          # L6 安全合规层
├── shardflow-frontend/        # 前端（React + TypeScript）
│   └── src/
│       ├── pages/             # 对话/知识库/画像/MCP/任务等页面
│       ├── components/        # 状态包可视化/策略面板/来源可视化等组件
│       └── api/               # API 客户端
├── shardflow-system/          # Java 外围服务（Spring Boot）
│   ├── shardflow-auth/        # 认证授权
│   ├── shardflow-profile/     # 用户画像
│   ├── shardflow-shard/       # 状态包管理
│   ├── shardflow-strategy/    # 策略管理 + Milvus 向量检索
│   ├── shardflow-mcp/         # MCP 注册中心
│   ├── shardflow-kb/          # 知识库/文档管理
│   ├── shardflow-config/      # Agent 配置/自定义模型
│   ├── shardflow-task/        # 任务管理
│   └── shardflow-callback/    # 回调接收
├── docker/                    # Docker Compose 编排
│   ├── docker-compose.yml     # 开发环境
│   ├── docker-compose.agent.yml
│   └── docker-compose.prod.yml
└── docs/                       # 项目文档
    ├── spec/                  # 产品规格与需求
    ├── design/                # 架构设计
    ├── development/           # 开发规范
    └── knowledge/             # 知识规范
```

---

## 快速开始

### 环境要求

- Java 21+
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- PostgreSQL 18
- Redis 7
- Milvus 2.5

### 1. 启动基础服务

```bash
cd docker
docker-compose up -d
```

### 2. 启动 Java 外围服务

```bash
cd shardflow-system
mvn clean package -DskipTests
java -jar shardflow-app/target/shardflow-app.jar
```

### 3. 启动 Python 推理层

```bash
cd shardflow-agent
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 启动前端

```bash
cd shardflow-frontend
npm install
npm run dev
```

访问 `http://localhost:5173` 即可使用。

---

## License

[MIT](LICENSE)
