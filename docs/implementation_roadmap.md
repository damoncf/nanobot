# nanobot 多模式改造实施路线图

## 快速决策参考

---

## 1. 架构概览

```
当前架构                          目标架构
──────────                       ──────────
┌─────────┐                     ┌──────────────────┐
│ CLI/    │                     │ CLI/Channels     │
│ Channels│                     └────────┬─────────┘
└────┬────┘                              │
     │                            ┌──────▼──────┐
     ▼                            │ Mode Router │
┌─────────┐                     └──────┬──────┘
│Message  │                            │
│Bus      │         ┌──────────────────┼──────────────────┐
└────┬────┘         ▼                  ▼                  ▼
     │       ┌──────────┐      ┌──────────┐      ┌──────────────┐
     ▼       │ ASK Mode │      │ PLAN Mode│      │ AGENT Mode   │
┌─────────┐  └──────────┘      └────┬─────┘      └──────┬───────┘
│ Agent   │                         │                   │
│ Loop    │                         ▼                   ▼
└────┬────┘                  ┌────────────┐      ┌──────────────┐
     │                       │ TaskFlow   │      │ Checkpoint   │
     ▼                       │ Engine     │      │ + TaskMemory │
┌─────────┐                  └─────┬──────┘      └──────┬───────┘
│ Tools   │                        │                   │
└─────────┘                        └─────────┬─────────┘
                                             │
                              ┌──────────────▼──────────────┐
                              │ Enhanced Memory System      │
                              │ (Working + Episodic +       │
                              │  Semantic)                  │
                              └─────────────────────────────┘
```

---

## 2. 模块拆分与依赖

```
nanobot/
├── modes/                    # 新增: 模式系统
│   ├── __init__.py
│   ├── router.py            # 模式路由器
│   ├── base.py              # ModeProcessor基类
│   ├── ask.py               # ASK模式实现
│   ├── plan.py              # PLAN模式实现
│   └── agent.py             # AGENT模式增强
│
├── taskflow/                 # 新增: 任务流引擎
│   ├── __init__.py
│   ├── models.py            # 数据模型
│   ├── dag.py               # DAG执行器
│   ├── engine.py            # 任务流引擎
│   ├── store.py             # 持久化存储
│   └── checkpoint.py        # 检查点管理
│
├── memory/                   # 新增: 增强记忆系统
│   ├── __init__.py
│   ├── working.py           # 工作记忆 (L1)
│   ├── episodic.py          # 情景记忆 (L2)
│   ├── semantic.py          # 语义记忆 (L3)
│   └── retrieval.py         # 检索融合
│
├── agent/                    # 现有: 核心Agent
│   ├── loop.py              # 修改: 集成mode router
│   ├── memory.py            # 现有: 保留兼容
│   └── ...
│
└── cli/                      # 修改: 新增命令
    └── commands.py
```

---

## 3. 关键技术决策

### 决策 1: 模式切换机制

```python
# 选项 A: 显式切换（推荐）
User: "切换到plan模式"
Bot: "已切换到PLAN模式，我会为复杂任务创建执行计划。"

# 选项 B: 自动检测
User: "帮我写一个爬虫"
Bot: "[Auto-detect: 复杂任务 → PLAN模式]"

# 选项 C: 混合模式（最终实现）
自动检测 + 允许显式覆盖 + 智能建议
```

**决策**: 先实现A，再实现B，最终C

### 决策 2: 任务流存储

```
选项对比:
┌──────────────┬──────────┬──────────┬──────────┐
│     方案     │  复杂度  │  可靠性  │  性能   │
├──────────────┼──────────┼──────────┼──────────┤
│ JSONL文件    │    低    │   中     │   低    │
│ SQLite       │    中    │   高     │   中    │  ★推荐
│ PostgreSQL   │    高    │   高     │   高    │
└──────────────┴──────────┴──────────┴──────────┘
```

**决策**: SQLite（单文件，无外部依赖）

### 决策 3: 向量数据库

```python
# 配置示例
{
  "memory": {
    "semantic": {
      "provider": "chroma",  # 默认
      # "provider": "faiss",   # 高性能选项
      # "provider": "qdrant",  # 大规模选项
      # "provider": None,      # 禁用向量记忆
    }
  }
}
```

**决策**: Chroma为默认，可选禁用

---

## 4. 数据库 Schema

```sql
-- taskflow.db

-- 任务表
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    session_key TEXT NOT NULL,
    goal TEXT NOT NULL,
    mode TEXT NOT NULL,  -- 'plan' | 'agent'
    status TEXT NOT NULL, -- 'pending' | 'running' | 'paused' | 'completed' | 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    metadata JSON
);

-- 任务步骤表 (PLAN模式)
CREATE TABLE task_steps (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    description TEXT NOT NULL,
    depends_on TEXT,  -- JSON array of step_ids
    status TEXT DEFAULT 'pending',
    result JSON,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- 检查点表 (AGENT模式)
CREATE TABLE checkpoints (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    iteration INTEGER NOT NULL,
    messages JSON NOT NULL,  -- 序列化消息历史
    context JSON,            -- 额外上下文
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- 记忆索引表
CREATE TABLE memory_index (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding_id TEXT,      -- 向量存储中的ID
    memory_type TEXT,       -- 'episodic' | 'semantic'
    task_id TEXT,
    session_key TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON
);

-- 创建索引
CREATE INDEX idx_tasks_session ON tasks(session_key);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_steps_task ON task_steps(task_id);
CREATE INDEX idx_checkpoints_task ON checkpoints(task_id);
```

---

## 5. 核心接口定义

```python
# modes/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class ModeContext:
    message: str
    session: Session
    history: list[dict]
    memory: MemorySnapshot
    config: ModeConfig

@dataclass  
class ModeResult:
    content: str
    mode: str  # 'ask' | 'plan' | 'agent'
    requires_action: bool = False  # 是否需要用户确认
    action_type: str | None = None  # 'approve_plan' | 'provide_input' | etc.
    action_payload: dict | None = None

class ModeProcessor(ABC):
    @abstractmethod
    async def process(self, ctx: ModeContext) -> ModeResult:
        """处理用户消息"""
        pass
    
    @abstractmethod
    def should_handle(self, message: str, history: list) -> float:
        """
        返回置信度 0.0-1.0
        用于自动模式选择
        """
        pass


# taskflow/engine.py
class TaskFlowEngine:
    async def create_task(
        self, 
        goal: str,
        mode: str,
        session_key: str,
        options: TaskOptions
    ) -> Task:
        """创建新任务"""
        pass
    
    async def execute_task(self, task_id: str) -> ExecutionResult:
        """执行任务"""
        pass
    
    async def pause_task(self, task_id: str) -> None:
        """暂停任务"""
        pass
    
    async def resume_task(self, task_id: str) -> ExecutionResult:
        """从检查点恢复"""
        pass
    
    async def get_task_status(self, task_id: str) -> TaskStatus:
        """获取任务状态"""
        pass


# memory/enhanced.py
class EnhancedMemorySystem:
    async def retrieve(
        self,
        query: str,
        context: RetrievalContext
    ) -> RetrievedContext:
        """
        三层检索:
        1. Working Memory (当前会话)
        2. Episodic Memory (历史任务)
        3. Semantic Memory (知识库)
        """
        pass
    
    async def consolidate(self, session: Session) -> None:
        """记忆固化"""
        pass
```

---

## 6. Phase 实施计划

### Phase 1: 基础框架 (Week 1)

**目标**: 模式系统骨架

```bash
# 任务清单
[ ] 创建 modes/ 模块结构
[ ] 实现 ModeRouter
[ ] 实现 ModeProcessor 基类
[ ] 实现 ASK模式 (基础版)
[ ] 添加 mode 切换命令
[ ] 单元测试覆盖 > 70%
```

**交付物**:
- `nanobot mode ask` 可用
- 自动路由基础框架
- 文档更新

---

### Phase 2: PLAN模式 (Week 2-3)

**目标**: 任务规划与执行

```bash
# Week 2
[ ] TaskPlan 数据模型
[ ] PlanModeProcessor.create_plan()
[ ] 用户确认流程
[ ] 计划展示格式 (Markdown)

# Week 3
[ ] DAG执行引擎
[ ] 步骤依赖解析
[ ] 进度追踪
[ ] 暂停/恢复功能
[ ] 任务状态管理
```

**交付物**:
- `nanobot mode plan` 可用
- 任务创建 → 确认 → 执行完整流程
- 状态持久化

---

### Phase 3: AGENT增强 (Week 4)

**目标**: 自主模式增强

```bash
[ ] Checkpoint/Resume机制
[ ] 增强循环 (反思、重试)
[ ] TaskMemory集成
[ ] 长期运行支持
[ ] 错误恢复策略
```

**交付物**:
- AGENT模式可恢复
- 跨会话记忆
- 复杂任务成功率 > 80%

---

### Phase 4: 记忆系统 (Week 5)

**目标**: 三层记忆架构

```bash
[ ] Chroma集成 (可选依赖)
[ ] Embedding Provider抽象
[ ] Working Memory增强
[ ] Episodic Memory实现
[ ] Semantic Memory实现
[ ] 检索融合算法
```

**交付物**:
- 向量记忆可选启用
- 自动记忆 consolidation
- 相关经验检索

---

### Phase 5: 集成优化 (Week 6)

**目标**: 完整集成与优化

```bash
[ ] 全模式集成测试
[ ] 性能基准测试
[ ] 配置简化
[ ] 文档完善
[ ] 向后兼容验证
```

**交付物**:
- v0.2.0 发布
- 完整文档
- 迁移指南

---

## 7. 关键代码片段

### 7.1 Mode Router

```python
# modes/router.py
class ModeRouter:
    def __init__(self):
        self.processors = {
            'ask': AskModeProcessor(),
            'plan': PlanModeProcessor(),
            'agent': AgentModeProcessor(),
        }
        self.classifier = IntentClassifier()
    
    async def route(
        self, 
        message: str,
        session: Session,
        forced_mode: str | None = None
    ) -> ModeResult:
        # 显式模式切换
        if message.lower().startswith('/mode '):
            return self._handle_mode_switch(message, session)
        
        # 强制模式
        if forced_mode:
            processor = self.processors[forced_mode]
            return await processor.process(ctx)
        
        # 自动检测
        mode = await self._auto_classify(message, session)
        processor = self.processors[mode]
        
        ctx = ModeContext(
            message=message,
            session=session,
            history=session.get_history(),
            memory=await self._load_memory(session),
            config=self._get_mode_config(mode)
        )
        
        return await processor.process(ctx)
    
    async def _auto_classify(self, message: str, session: Session) -> str:
        """自动模式分类"""
        scores = {}
        for mode, processor in self.processors.items():
            scores[mode] = processor.should_handle(message, session.get_history())
        
        # 阈值判断
        if scores['ask'] > 0.8:
            return 'ask'
        if scores['plan'] > 0.7:
            return 'plan'
        return 'agent'
```

### 7.2 PLAN模式核心

```python
# modes/plan.py
class PlanModeProcessor(ModeProcessor):
    async def process(self, ctx: ModeContext) -> ModeResult:
        # 1. 分析是否需要创建新计划
        if not self._has_active_plan(ctx.session):
            # 创建计划
            plan = await self._create_plan(ctx)
            
            return ModeResult(
                content=plan.to_markdown(),
                mode='plan',
                requires_action=True,
                action_type='approve_plan',
                action_payload={'plan_id': plan.id}
            )
        
        # 2. 处理用户确认
        if self._is_approval(ctx.message):
            task = await self.engine.start_plan_execution(
                plan_id=self._get_pending_plan(ctx.session)
            )
            return ModeResult(
                content=f"开始执行任务，ID: {task.id}",
                mode='plan'
            )
        
        # 3. 查询任务状态
        if self._is_status_query(ctx.message):
            status = await self.engine.get_task_status(...)
            return ModeResult(content=status.to_markdown(), mode='plan')
    
    async def _create_plan(self, ctx: ModeContext) -> TaskPlan:
        """调用LLM创建计划"""
        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": PLANNING_PROMPT},
                {"role": "user", "content": ctx.message}
            ],
            tools=[CREATE_PLAN_TOOL],
            model=self.config.planning_model
        )
        
        if response.has_tool_calls:
            plan_data = response.tool_calls[0].arguments
            return TaskPlan.from_llm_output(plan_data)
```

### 7.3 Checkpoint机制

```python
# taskflow/checkpoint.py
class CheckpointManager:
    async def save(
        self,
        task_id: str,
        iteration: int,
        state: AgentState
    ) -> Checkpoint:
        """保存检查点"""
        checkpoint = Checkpoint(
            id=generate_id(),
            task_id=task_id,
            iteration=iteration,
            messages=serialize_messages(state.messages),
            context=state.context,
            created_at=now()
        )
        
        # 存储到数据库
        await self.store.save_checkpoint(checkpoint)
        
        # 清理旧检查点 (保留最近3个)
        await self._cleanup_old_checkpoints(task_id, keep=3)
        
        return checkpoint
    
    async def load_latest(self, task_id: str) -> Checkpoint | None:
        """加载最新检查点"""
        return await self.store.get_latest_checkpoint(task_id)
    
    async def resume_from(
        self, 
        checkpoint: Checkpoint
    ) -> AgentState:
        """从检查点恢复状态"""
        return AgentState(
            messages=deserialize_messages(checkpoint.messages),
            context=checkpoint.context,
            iteration=checkpoint.iteration
        )
```

---

## 8. 测试策略

```python
# 测试覆盖矩阵

# Unit Tests
modes/tests/test_router.py       # 路由逻辑
modes/tests/test_ask.py          # ASK模式
modes/tests/test_plan.py         # PLAN模式
taskflow/tests/test_dag.py       # DAG执行
taskflow/tests/test_engine.py    # 任务流引擎
memory/tests/test_semantic.py    # 向量记忆

# Integration Tests
tests/integration/test_mode_switch.py      # 模式切换
tests/integration/test_plan_execution.py   # 计划执行
tests/integration/test_checkpoint.py       # 检查点恢复
tests/integration/test_memory_layers.py    # 三层记忆

# E2E Tests
tests/e2e/test_full_workflow.py  # 完整工作流
```

---

## 9. 发布 checklist

- [ ] 所有Phase完成
- [ ] 测试覆盖率 > 80%
- [ ] 性能基准通过
- [ ] 文档完整
- [ ] 配置迁移脚本
- [ ] 向后兼容验证
- [ ] 版本号更新 (v0.2.0)
- [ ] CHANGELOG更新
- [ ] 发布说明

---

## 10. 相关文档

1. `agent_mode_technical_feasibility.md` - 技术可行性分析
2. `alternative_technical_solutions.md` - 替代方案对比
3. `implementation_roadmap.md` - 本文件 (实施路线图)

---

*制定日期: 2026-03-07*  
*目标版本: nanobot v0.2.0*
