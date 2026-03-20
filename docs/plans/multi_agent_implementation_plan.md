# 基于当前 nanobot 的多智能体实现方案

- 文档状态：Draft v0.1
- 对应需求：`docs/specs/multi_agent_requirements_spec.md`
- 设计原则：尽量复用现有代码路径，先做可落地版本，再考虑任务流引擎化

## 1. 当前基础能力评估

nanobot 已经具备多智能体首版落地所需的几块基础设施：

| 现有能力 | 位置 | 可直接复用内容 |
| --- | --- | --- |
| 主执行循环 | `nanobot/agent/loop.py` | 统一入口、工具循环、系统消息处理、取消控制 |
| 子智能体执行 | `nanobot/agent/subagent.py` | 后台运行、工具受限、结果回传、按会话取消 |
| 子智能体派发工具 | `nanobot/agent/tools/spawn.py` | 从主循环发起子任务 |
| 消息路由 | `nanobot/bus/queue.py` | 主体与子任务的异步解耦 |
| 会话持久化 | `nanobot/session/manager.py` | JSONL 会话落盘、追加写入 |
| 长期记忆 | `nanobot/agent/memory.py` | `MEMORY.md`、`HISTORY.md`、增量固化 |
| 系统上下文构建 | `nanobot/agent/context.py` | 统一注入系统提示、记忆、技能摘要 |

结论：nanobot 已经具备“主循环 + 子执行体 + 异步回传”的雏形，但缺少正式的协作协议和持久化产物层。

## 2. 当前缺口

与正式多智能体需求相比，当前实现的主要缺口如下：

1. `spawn` 只能提交自由文本任务，不能表达结构化任务单。
2. `SubagentManager` 返回的是自然语言公告，不是结构化回执单。
3. 系统缺少任务书、任务单、回执单、任务日志的本地存储规范。
4. Sub Agent 当前没有显式继承任务书、历史摘要和任务级共享上下文。
5. 没有 Main Agent 侧的任务协调器来管理派发、回收、合并与状态推进。
6. “共享记忆”目前只有全局 `MEMORY.md`，没有任务级共享上下文层。
7. 现有 `/stop` 能取消任务，但没有任务级状态文件与恢复点。
8. 当前 `SubagentManager` 只接受初始化时的默认模型，不能按子任务指定模型或资源配额。

## 3. 实现原则

### 3.1 先协议，后调度

首版先把“任务书 / 任务单 / 回执单 / 日志”做实，再考虑复杂的 DAG、审批流和自动模式路由。没有结构化协作协议，后续调度层很难稳定。

### 3.2 先文件化，后数据库化

基于当前 nanobot 的轻量化风格，首版建议使用工作区本地文件作为任务存储，而不是立即引入 SQLite 或外部数据库。原因如下：

1. 当前会话和记忆系统已经采用文件持久化。
2. 任务书、任务单、回执单天然适合人类直接查看。
3. 首版目标是形成可用闭环，而不是一次性做成完整工作流平台。

如果后续进入复杂任务图、多任务恢复和跨会话查询阶段，再引入 SQLite 更合适。

### 3.3 Main 为事实源

首版不单独重写一个“MainAgent”类，而是继续以 `AgentLoop` 作为 Main Agent 的执行壳，在其上增加协作协调器。这样可以保留当前主路径，避免将单智能体逻辑整体推翻。

### 3.4 共享可见，主写从提议

全局长期记忆仍由 Main Agent 负责写入。Sub Agent 写任务级产物和日志，通过结构化回执将结果交给 Main 合并。

## 4. 目标架构

```text
User / Channel
      |
      v
  AgentLoop (继续作为 Main Agent 外壳)
      |
      +--> CollaborationCoordinator
      |        |
      |        +--> TaskStore
      |        +--> TaskSpec / WorkOrder / Receipt / TaskLog
      |
      +--> ToolRegistry
      |        |
      |        +--> spawn(structured)
      |
      +--> SubagentManager
               |
               +--> SubAgent tool loop
               +--> receipt.json
               +--> system event back to Main
```

## 5. 推荐的目录与数据布局

建议在工作区新增 `tasks/` 目录：

```text
workspace/
├── memory/
├── sessions/
└── tasks/
    └── <task_id>/
        ├── task_spec.json
        ├── task_spec.md
        ├── shared_context.md
        ├── task_log.md
        ├── work_orders/
        │   └── <work_order_id>.json
        ├── receipts/
        │   └── <receipt_id>.json
        └── artifacts/
            └── ...
```

说明：

1. `task_spec.json` 是机器可读的主事实源。
2. `task_spec.md` 是人类友好的镜像文档，便于审查。
3. `task_spec.json` 中应包含任务级 `resource_policy`，用于定义默认模型、并发和预算边界。
4. `work_orders/*.json` 中应包含子任务级 `resource_profile`，用于指定该子任务实际使用的模型和执行配额。
5. `shared_context.md` 存放该任务的共享上下文摘要。
6. `task_log.md` 为追加写入事件日志。
7. `artifacts/` 存放任务相关输出文件。

## 6. 模块改造建议

### 6.1 新增 `nanobot/agent/collaboration/models.py`

定义任务协作数据模型：

1. `TaskSpec`
2. `WorkOrder`
3. `Receipt`
4. `TaskEvent`
5. `ResourcePolicy` / `ResourceProfile`

建议使用 `dataclass`，保持与当前项目风格一致。

### 6.2 新增 `nanobot/agent/collaboration/store.py`

负责文件落盘、读取和状态更新，提供以下能力：

1. 创建任务目录。
2. 写入和更新任务书。
3. 写入任务单。
4. 写入回执单。
5. 追加任务日志。
6. 查询任务状态。

### 6.3 新增 `nanobot/agent/collaboration/coordinator.py`

该模块是首版多智能体的核心协调器，负责：

1. 根据用户请求创建任务书。
2. 生成和派发任务单。
3. 接收回执并更新任务状态。
4. 决定是否继续派发补充子任务。
5. 为每个子任务分配资源配置，如指定模型、预算和超时。
6. 将结果整理回 Main Agent 当前上下文。

这里不建议一上来把协调逻辑直接塞进 `AgentLoop`，否则会使主循环继续膨胀。

### 6.4 修改 `nanobot/agent/tools/spawn.py`

将当前自由文本参数升级为兼容结构化载荷，例如：

```json
{
  "task": "为用户整理 API 文档差异",
  "label": "文档差异分析",
  "task_id": "task_xxx",
  "work_order_id": "wo_xxx",
  "context_files": [
    "tasks/task_xxx/shared_context.md"
  ],
  "resource_profile": {
    "model": "anthropic/claude-sonnet-4-5",
    "max_iterations": 12,
    "timeout_s": 300
  },
  "expected_output": "receipt"
}
```

兼容策略：

1. 继续兼容旧的 `task + label` 形式。
2. 若传入 `task_id` 和 `work_order_id`，则按结构化任务单执行。

### 6.5 修改 `nanobot/agent/subagent.py`

当前 `SubagentManager` 已能独立跑一个轻量工具循环，但需要增强：

1. 在启动时读取任务单和共享上下文。
2. 将系统提示从“自由任务执行”升级为“根据任务单执行并返回结构化回执”。
3. 支持按 `resource_profile` 覆写默认模型，并执行最大迭代次数、超时等资源限制。
4. 完成后写入 `receipt.json`，而不是只拼自然语言公告。
5. 通过 `InboundMessage.metadata` 回传结构化事件，例如：

```json
{
  "event": "subagent_receipt",
  "task_id": "task_xxx",
  "work_order_id": "wo_xxx",
  "receipt_path": "tasks/task_xxx/receipts/rcpt_xxx.json"
}
```

这比依赖 LLM 再解析自然语言公告稳定得多。

### 6.6 修改 `nanobot/agent/loop.py`

在不破坏现有主路径的前提下增加以下能力：

1. 初始化 `CollaborationCoordinator`。
2. 在普通用户消息进入时，允许 Main Agent 选择创建任务书并调用结构化 `spawn`。
3. 在处理 `channel="system"` 消息时，如果 `metadata.event == "subagent_receipt"`，先走协调器合并逻辑，再决定是否调用 LLM 向用户解释。
4. 保留现有 `/stop` 逻辑，并同步更新任务状态为 `cancelled`。

### 6.7 可选修改 `nanobot/agent/context.py`

为 Main Agent 增加任务级上下文注入能力，例如：

1. 当前活跃任务摘要。
2. 未完成任务单概览。
3. 最近回执摘要。

这样 Main Agent 在多轮对话中可以持续“记得”正在协作的任务，而不必每次靠用户重复提醒。

## 7. 任务执行流

建议的首版执行流如下：

1. 用户发起复杂任务。
2. `AgentLoop` 作为 Main Agent 判断该任务适合多智能体协作。
3. `CollaborationCoordinator` 创建 `task_spec.json`、`task_spec.md` 和初始 `task_log.md`。
4. Main Agent 生成一个或多个 `WorkOrder`，并为每个子任务写入 `resource_profile`，落盘到 `work_orders/`。
5. Main Agent 调用增强后的 `spawn`，把 `task_id`、`work_order_id`、`context_files` 和 `resource_profile` 传给 `SubagentManager`。
6. `SubagentManager` 启动 Sub Agent，加载任务单与共享上下文，并按资源配置选择模型和执行受限工具循环。
7. Sub Agent 完成后生成 `receipt.json` 并通过消息总线发送结构化 system event。
8. `AgentLoop` 接收 event，`CollaborationCoordinator` 读取回执、更新任务书和任务日志。
9. 如果还有未完成子任务，Main Agent 可继续派发。
10. 当任务满足成功标准后，Main Agent 统一向用户输出最终结果。

## 8. 上下文与记忆策略

### 8.1 Main Agent

Main Agent 继续使用当前 `ContextBuilder` 的完整系统上下文，包括：

1. 工作区引导文件。
2. 全局 `MEMORY.md`。
3. 技能摘要。
4. 会话历史。

### 8.2 Sub Agent

Sub Agent 不应直接继承 Main Agent 的全部上下文，而是使用以下裁剪包：

1. 任务单。
2. 任务书摘要。
3. 共享上下文摘要。
4. 与该子任务直接相关的文件引用。
5. 必要的长期记忆摘录。
6. 该子任务的 `resource_profile`。

这能控制 token 成本，也更接近“任务上下文一致”而非“原始消息完全复制”。

### 8.3 共享记忆实现

首版建议使用双层共享策略：

1. 全局层：继续使用 `memory/MEMORY.md` 和 `memory/HISTORY.md`，只允许 Main Agent 最终写入。
2. 任务层：新增 `tasks/<task_id>/shared_context.md` 和 `task_log.md`，Main 与 Sub 均可读，Sub 仅能追加任务级产物。

## 9. 渐进式交付建议

### Phase 1：协议落地

目标：把任务书、任务单、回执单、任务日志落盘，并打通结构化派发与回传。

范围：

1. 新增 models/store/coordinator。
2. `spawn` 兼容结构化参数。
3. `subagent` 输出 `receipt.json`。
4. `AgentLoop` 识别 receipt 事件。

### Phase 2：持续协作

目标：让 Main Agent 在多轮对话中持续维护活跃任务。

范围：

1. 任务状态管理。
2. 多轮继续派发。
3. 任务摘要注入主上下文。
4. `/stop` 与任务状态联动。

### Phase 3：增强调度

目标：支持更稳定的并发和依赖控制。

范围：

1. 简单依赖关系。
2. 限制并发数。
3. 重试策略。
4. 更细粒度的工具白名单。

### Phase 4：再考虑任务流引擎化

当以下需求出现时，再考虑引入 SQLite 或更完整的 taskflow：

1. 需要跨会话检索历史任务。
2. 需要复杂 DAG 依赖。
3. 需要可靠恢复和批量管理。
4. 需要面向多个任务的状态查询接口。

## 10. 测试建议

### 单元测试

1. `TaskStore` 的创建、写入、状态更新。
2. `spawn` 对结构化参数和旧参数的兼容性。
3. `SubagentManager` 生成回执单并发布结构化事件。
4. `CollaborationCoordinator` 对回执合并和任务状态推进。

### 集成测试

1. 单个 Sub Agent 完成任务并被 Main Agent 汇总。
2. 两个 Sub Agent 并行执行并合并结果。
3. 一个 Sub Agent 失败后触发重试或降级。
4. 用户调用 `/stop` 后主任务和子任务同步取消。

### 回归测试

1. 普通单智能体对话不受影响。
2. 原有 `spawn(task, label)` 路径继续可用。
3. 会话保存与记忆固化不被破坏。

## 11. 风险与控制

### 风险 1：Sub Agent 上下文不足

如果只派发一句自然语言任务，Sub Agent 很容易重复向 Main 询问或做出错误假设。

控制方式：

1. 强制任务单结构化。
2. 强制传入共享上下文文件。

### 风险 2：共享记忆污染

如果 Sub Agent 直接写全局记忆，容易将中间结论或错误结果写进长期记忆。

控制方式：

1. Sub Agent 不直接写 `MEMORY.md`。
2. Main Agent 合并后再写全局记忆。

### 风险 3：主循环复杂度继续膨胀

如果所有协调逻辑都堆在 `AgentLoop` 中，会使主循环进一步难维护。

控制方式：

1. 新增 `CollaborationCoordinator` 承担协作逻辑。
2. `AgentLoop` 只做路由、触发和结果回传。

### 风险 4：并发任务状态不一致

多个 Sub Agent 同时回执时，任务书可能出现覆盖写入。

控制方式：

1. `TaskStore` 更新采用单任务级串行写策略。
2. 回执文件先落盘，再更新任务书状态。

## 12. 结论

对当前 nanobot 而言，最合适的首版多智能体方案不是直接上完整 taskflow 引擎，而是沿用现有 `AgentLoop + spawn + SubagentManager + MessageBus + Session/Memory` 主骨架，在其上补齐协作协议和任务产物层。

这样做有三个直接收益：

1. 与现有代码风格一致，改动面可控。
2. 能快速把草稿里的“任务书 / 任务单 / 回执单 / 任务日志”变成可执行能力。
3. 为后续是否引入更重的模式路由、状态机和数据库存储保留演进空间。
