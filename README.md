# 经管之星 · 生产级经营分析 Agent

这是一个 React + FastAPI + LangGraph 实现的经营管理问答系统，覆盖首页看板、智能问数、多接口分析、业务 Skill 管理、调用审计、回复校对、接口管理和应用配置。

## 启动

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
.venv/bin/python run.py
```

默认访问地址：

```text
http://127.0.0.1:8000
```

默认复用 `data/jingguan_star.db`。数据库不存在时会根据 `db_schema.sql` 初始化结构；Docker 首次启动会从只读 seed 数据库复制初始数据。

## Docker 部署

构建镜像：

```bash
docker build -t jingguan-star:local .
```

直接运行容器：

```bash
docker run --rm -p 8000:8000 -v jingguan-star-data:/app/data jingguan-star:local
```

或使用 Docker Compose 后台启动：

```bash
docker compose up -d --build
```

浏览器访问：

```text
http://127.0.0.1:8000
```

查看运行状态和日志：

```bash
docker compose ps
docker compose logs -f --tail=200 jingguan-star
```

应用日志输出到 stdout，由 Docker/systemd 接管，不会额外写入项目目录里的 `logs/` 文件。
日志包含启动信息、API 请求状态与耗时、Agent run/node 状态、接口执行结果、模型调用失败原因和异常堆栈；接口调用参数仍以审计形式保存在 SQLite 的 `ai_query_call_audit` 表。

裸机 systemd 部署时查看日志：

```bash
sudo journalctl -u jingguan-star -f -n 200
```

停止服务：

```bash
docker compose down
```

## 开发模式

后端：

```bash
RELOAD=true .venv/bin/python run.py
```

前端：

```bash
cd frontend
npm run dev
```

Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 核心架构

- AI 不生成 SQL，不直接访问数据库。
- React + TypeScript 前端按业务领域拆分，不再使用原生 JS 页面脚本。
- FastAPI 后端按路由、仓储、服务与基础设施拆分。
- LangGraph 显式执行“意图识别 → Skill 匹配 → 查询计划 → 白名单审批 → 多接口执行 → 数据校验 → 回答生成”，并接入 `langgraph-checkpoint`：
  - 默认 `SqliteSaver`（`data/agent_checkpoints.db`）持久化每个 run 的 Agent 状态，进程崩溃可从最后一个 checkpoint 恢复；也支持 `MemorySaver`（`AGENT_CHECKPOINTER=memory`）。
  - 每个 run 写入 `agent_run` 台账，可通过 `GET /api/qa/sessions/{id}/runs` 与 `.../runs/{runId}/checkpoints` 回放调试。
  - 查询计划支持按接口策略人工介入：接口目录中标记为“调用前审批”的接口被规划调用时，图在白名单审批节点 `interrupt()`，前端展示待审批面板，通过/拒绝后经 `POST /api/qa/sessions/{id}/approve` 从持久化状态恢复执行。
- Skill / Playbook 匹配改为“LLM 语义选择 + 向量召回 + 关键词兜底”，不再是纯关键词打分：
  - 匹配阶段只把 Skill 摘要（code/name/description/触发词）放进 Agent 提示词，不把全部 Skill 步骤塞进模型；命中后才按 code 懒加载完整编排。
  - Skill 是可审计的业务操作手册，步骤支持 `stepId`、`dependsOn`、`paramSources` 和内置 `transform`，可表达“先查 A/C，再处理结果，最后把结果作为 B/D 的查询条件”。
  - `AGENT_SKILL_MATCH=auto` 默认先让 LLM 按语义选 Skill，模型不可用或未命中时用字符 n-gram TF-IDF 向量相似度（离线、无额外依赖）兜底，最后才是关键词评分。
- 智能问数可根据一个问题规划并执行多个启用的白名单接口。
- 后端确定性计算目标缺口、整体完成率、风险敞口、风险收入比、产品线贡献等派生经营指标，模型只负责解释和组织表达。
- 后端统一做接口状态、参数白名单、字段白名单和 `pageSize <= 100` 校验。
- 所有问数接口调用都会写入 `ai_query_call_audit`。
- 所有大模型调用（意图识别、Skill 匹配、查询规划、结构化回答、自然语言回答）都通过 `stream=true` 消费上游 OpenAI / DeepSeek Chat Completions 的 SSE token 流；
  自然语言回答把 token 增量实时推给前端（不是接口层事后切片的假流式），结构化 JSON 节点在传输层流式接收后返回完整解析结果；`stream_enabled` 关闭时退化为一次返回。
- 模型配置保存到 SQLite；支持 OpenAI 与 DeepSeek V4 的 OpenAI 兼容 Chat Completions；问答请求必须通过已配置的大模型。
- 同一问答会话会将最近历史消息带入大模型，用于理解追问、省略指标和延续筛选条件，避免长会话污染当前规划。
- 查询到数据时，问答结果固定展示为“数据发现、数据表格、数据统计、数据可视化”；图表由大模型选择单图、组合图或多图分开展示，并通过本地 ECharts 渲染。
- 问答结果内置可折叠“分析过程”，展示 Skill 命中、查询计划、接口调用、返回规模和节点耗时。
- 系统管理包含接口管理和应用配置；应用配置支持欢迎语开关与开场问题、下一步建议开关与数量、常问开关与频次阈值，以及模型配置。
- 下一步建议的具体问题由大模型基于本轮问题、回答和数据动态生成。
- 常问规则：同一问题连续提问达到应用配置中的阈值后自动进入常问列表，并可从问答页“常问”入口快速发起。

完整设计与实施记录：

- [`docs/production-architecture.md`](docs/production-architecture.md)
- [`docs/implementation-plan.md`](docs/implementation-plan.md)
- [`docs/agent-playbook-design.md`](docs/agent-playbook-design.md)
- [`docs/deployment-runbook.md`](docs/deployment-runbook.md)

## 智能问数流程

```text
用户提问
  -> 意图识别
  -> 业务 Skill / Playbook 匹配
  -> 生成单接口或多接口查询计划
  -> 确定性白名单审批
  -> 执行注册的固定查询处理器并逐调用审计
  -> 校验返回字段、规模和结果结构
  -> 基于全部已验证数据组织回答
  -> 通过 SSE 将模型 token 流增量返回到问答页
```

## 验证

```bash
cd frontend && npm run typecheck && npm run build
cd .. && .venv/bin/python -m unittest discover -s tests -v
```

## DeepSeek V4

系统管理 / 应用配置 / 模型配置中可以选择 `DeepSeek V4`，并一键切换：

- `deepseek-v4-pro`
- `deepseek-v4-flash`

DeepSeek V4 默认 Base URL：

```text
https://api.deepseek.com
```

## 主要 API

- `GET /api/dashboard`
- `GET|POST /api/query-interfaces`
- `GET|PUT|PATCH /api/query-interfaces/{interfaceCode}`
- `GET|POST /api/agent-skills`
- `POST /api/agent-skills/import`
- `GET|PUT|PATCH|DELETE /api/agent-skills/{skillCode}`
- `POST /api/ai-query/{interfaceCode}`
- `GET /api/ledgers/commercial`
- `GET /api/ledgers/ppl`
- `GET /api/ledgers/goals`
- `GET /api/audits`
- `GET /api/audits/{auditId}`
- `POST /api/qa/sessions/{sessionId}/messages/stream`
- `DELETE /api/qa/sessions/{sessionId}`
- `GET|POST /api/qa/feedback`
- `GET|PATCH /api/qa/feedback/{feedbackId}`
- `GET|PUT /api/llm-config`
- `GET|PUT /api/app-config`
- `GET /api/qa/frequent-questions`
