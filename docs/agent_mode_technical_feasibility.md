# nanobot 任务流与多模式架构改造方案

## 技术可行性评估报告

> 评估日期: 2026-03-07  
> 目标版本: v0.2.0  
> 评估人员: AI Architect

---

## 1. 当前架构分析

### 1.1 核心架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                         nanobot v0.1.4                          │
├─────────────────────────────────────────────────────────────────┤
│  Channels (10+)    │   Agent Loop    │    Memory System         │
│  - Telegram        │  - Tool Exec    │  - Session (JSONL)       │
│  - Discord         │  - Subagent     │  - Memory.md             │
│  - WhatsApp        │  - MCP Support  │  - History.md            │
│  - Feishu/Slack... │  - Heartbeat    │  - Consolidation         │
├─────────────────────────────────────────────────────────────────┤
│  Tools: file, shell, web, message, spawn, cron                  │
├─────────────────────────────────────────────────────────────────┤
│  Providers: OpenAI, Anthropic, DeepSeek, OpenRouter...          │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 当前数据流

```
InboundMessage → MessageBus → AgentLoop._process_message()
                                    ↓
SessionManager → ContextBuilder → LLMProvider
                                    ↓
ToolRegistry.execute() → OutboundMessage
```

### 1.3 现有能力评估

| 维度 | 当前状态 | 满足度 |
|------|---------|--------|
| 信息流处理 | ✅ 完整消息生命周期 | 100% |
| 工具调用 | ✅ 原子工具执行 | 90% |
| 子任务 | ✅ SubagentManager | 70% |
| 任务编排 | ❌ 无工作流概念 | 0% |
| 任务状态 | ❌ 仅session级 | 20% |
| 多模式切换 | ❌ 单一agent模式 | 0% |
| 长期记忆 | ⚠️ 基础consolidation | 60% |
| 跨会话记忆 | ❌ 无 | 0% |

---

## 2. 目标架构设计

### 2.1 三模式架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Mode Router                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐  │
│  │  ASK Mode   │  │  PLAN Mode  │  │        AGENT Mode           │  │
│  │             │  │             │  │                             │  │
│  │ Quick Q&A   │  │ Task Plan   │  │  Autonomous Execution       │  │
│  │ No tools    │  │ Breakdown   │  │  - Goal oriented            │  │
│  │ Direct LLM  │  │ Estimation  │  │  - Multi-step reasoning     │  │
│  │ Fast/Cheap  │  │ Approval    │  │  - Self-correction          │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 任务流核心架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                      TaskFlow Engine                                │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────────────┐ │
│  │ Task DAG │  │ Executor │  │  State   │  │ Checkpoint & Resume │ │
│  │ Manager  │  │ Engine   │  │  Store   │  │                     │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────────────────┘ │
├─────────────────────────────────────────────────────────────────────┤
│  Task States: pending → planning → approved → running → completed   │
│               ├─ failed ├─ retrying ├─ paused                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 改造方案详述

### 3.1 ASK Mode (问答模式)

#### 设计目标
- 快速响应，无工具调用
- 低成本（使用轻量级模型）
- 适合简单咨询、确认、闲聊

#### 技术实现

```python
# nanobot/modes/ask.py
class AskModeProcessor:
    """
    ASK模式处理器 - 直接LLM问答，无工具调用
    """
    
    def __init__(self, provider: LLMProvider, memory: MemoryStore):
        self.provider = provider
        self.memory = memory
    
    async def process(
        self, 
        message: str,
        session: Session,
        context: ContextSnapshot
    ) -> ModeResult:
        """
        ASK模式处理流程:
        1. 构建轻量级prompt（不包含tools）
        2. 直接调用LLM
        3. 返回文本响应
        """
        messages = self._build_ask_prompt(
            history=session.get_history(max_messages=10),
            current=message,
            memory=self.memory.get_relevant(message, k=3)  # 检索相关记忆
        )
        
        response = await self.provider.chat(
            messages=messages,
            tools=None,  # 无工具
            model=self._select_cheap_model(),  # 使用轻量模型
            max_tokens=1024,
        )
        
        return ModeResult(
            content=response.content,
            mode="ask",
            used_tools=False,
            tokens_used=response.usage
        )
    
    def _should_escalate(self, message: str) -> bool:
        """
        判断是否需要升级到PLAN/AGENT模式
        - 包含动作关键词（创建、修改、执行、搜索等）
        - 用户明确要求工具使用
        - 需要多步骤推理
        """
        action_keywords = [
            "create", "write", "edit", "modify", "delete",
            "execute", "run", "deploy", "search", "find",
            "analyze", "compare", "generate"
        ]
        return any(kw in message.lower() for kw in action_keywords)
```

#### 改造点
| 组件 | 改动 | 工作量 |
|------|------|--------|
| AgentLoop | 添加mode router | M |
| ContextBuilder | 支持tool-less prompt | S |
| Config | 添加ask_model配置 | S |
| Session | 记录mode类型 | S |

---

### 3.2 PLAN Mode (规划模式)

#### 设计目标
- 复杂任务分解与规划
- 用户确认后再执行
- 时间/资源估算
- 支持计划编辑

#### 技术实现

```python
# nanobot/modes/plan.py
class PlanModeProcessor:
    """
    PLAN模式处理器 - 任务规划与人工确认
    """
    
    PLANNING_TOOL = [
        {
            "type": "function",
            "function": {
                "name": "create_plan",
                "description": "Create a task plan with steps",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string"},
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "description": {"type": "string"},
                                    "tools_needed": {"type": "array", "items": {"type": "string"}},
                                    "estimated_time": {"type": "string"},
                                    "can_fail": {"type": "boolean"},
                                    "depends_on": {"type": "array", "items": {"type": "string"}}
                                }
                            }
                        },
                        "total_estimate": {"type": "string"},
                        "risk_level": {"type": "string", "enum": ["low", "medium", "high"]}
                    },
                    "required": ["goal", "steps"]
                }
            }
        }
    ]
    
    async def create_plan(
        self,
        message: str,
        session: Session
    ) -> TaskPlan:
        """创建任务计划"""
        
        # 分析任务复杂度
        complexity = await self._analyze_complexity(message)
        
        # 生成计划
        response = await self.provider.chat(
            messages=[
                {"role": "system", "content": self._get_planning_prompt(complexity)},
                {"role": "user", "content": f"Create a plan for: {message}"}
            ],
            tools=self.PLANNING_TOOL,
            model=self.reasoning_model,  # 使用推理模型
        )
        
        if response.has_tool_calls:
            plan_data = response.tool_calls[0].arguments
            return TaskPlan(
                id=generate_id(),
                goal=plan_data["goal"],
                steps=[PlanStep(**s) for s in plan_data["steps"]],
                status=PlanStatus.PENDING_APPROVAL,
                created_by=session.key,
                created_at=now()
            )
    
    async def execute_plan(
        self,
        plan: TaskPlan,
        approval: PlanApproval
    ) -> PlanExecution:
        """
        执行已批准的计划
        - 支持step-by-step执行
        - 支持暂停/恢复
        - 实时进度更新
        """
        execution = PlanExecution(plan=plan)
        
        # 构建DAG
        dag = self._build_dag(plan.steps)
        
        # 按依赖顺序执行
        for step_group in dag.topological_groups():
            # 并行执行无依赖的步骤
            results = await asyncio.gather(*[
                self._execute_step(step, execution)
                for step in step_group
            ])
            
            # 检查失败
            for step, result in zip(step_group, results):
                if not result.success and not step.can_fail:
                    execution.status = ExecutionStatus.FAILED
                    execution.failed_step = step.id
                    return execution
        
        execution.status = ExecutionStatus.COMPLETED
        return execution


@dataclass
class TaskPlan:
    """任务计划实体"""
    id: str
    goal: str
    steps: list[PlanStep]
    status: PlanStatus
    created_by: str
    created_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None
    
    def to_markdown(self) -> str:
        """转换为用户友好的markdown格式"""
        lines = [f"## 🎯 Goal: {self.goal}\n"]
        lines.append(f"**Estimate:** {self.total_estimate} | **Risk:** {self.risk_level}\n")
        lines.append("### Steps:\n")
        for step in self.steps:
            deps = f" (depends: {', '.join(step.depends_on)})" if step.depends_on else ""
            lines.append(f"{step.id}. {step.description}{deps}")
            lines.append(f"   Tools: {', '.join(step.tools_needed)} | Time: {step.estimated_time}")
        lines.append("\nReply **approve** to execute, or suggest modifications.")
        return "\n".join(lines)
```

#### 数据模型

```python
# nanobot/taskflow/models.py

class PlanStatus(Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"  # 用户要求修改
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class PlanStep:
    id: str
    description: str
    tools_needed: list[str]
    estimated_time: str
    can_fail: bool = False
    depends_on: list[str] = field(default_factory=list)
    
    # 执行时填充
    status: StepStatus = StepStatus.PENDING
    result: StepResult | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TaskFlowStore:
    """
    任务流持久化存储
    - SQLite/JSONL混合存储
    - 支持查询、索引
    """
    def __init__(self, workspace: Path):
        self.db_path = workspace / "taskflow.db"
        self._init_tables()
    
    def save_plan(self, plan: TaskPlan) -> None:
        """保存计划到数据库"""
        
    def get_active_plans(self, session_key: str) -> list[TaskPlan]:
        """获取会话的活跃计划"""
        
    def update_step_status(
        self, 
        plan_id: str, 
        step_id: str, 
        status: StepStatus,
        result: dict | None = None
    ) -> None:
        """更新步骤状态"""
```

#### 改造点
| 组件 | 改动 | 工作量 |
|------|------|--------|
| 新增 modes/ | ASK/PLAN/AGENT处理器 | L |
| 新增 taskflow/ | DAG引擎、状态机 | L |
| AgentLoop | 集成mode router | M |
| Session | 关联active_plan | S |
| CLI | plan管理命令 | M |

---

### 3.3 AGENT Mode (自主模式)

#### 设计目标
- 自主决策与执行
- 多步骤复杂任务
- 错误恢复与重试
- 长期运行任务支持

#### 技术实现

```python
# nanobot/modes/agent.py
class AgentModeProcessor:
    """
    AGENT模式处理器 - 全自主任务执行
    基于现有AgentLoop增强
    """
    
    def __init__(self, 
        loop: AgentLoop,
        task_memory: TaskMemory,  # 跨任务记忆
        checkpoint_store: CheckpointStore
    ):
        self.loop = loop
        self.task_memory = task_memory
        self.checkpoint_store = checkpoint_store
    
    async def execute_goal(
        self,
        goal: str,
        session: Session,
        options: AgentOptions
    ) -> AgentResult:
        """
        执行目标导向的自主任务
        """
        # 创建任务上下文
        task_ctx = TaskContext(
            goal=goal,
            session=session,
            max_iterations=options.max_iterations or 100,
            checkpoint_interval=options.checkpoint_interval or 10
        )
        
        # 尝试恢复checkpoint
        checkpoint = await self._try_resume(task_ctx)
        if checkpoint:
            messages = checkpoint.messages
            iteration = checkpoint.iteration
        else:
            messages = self._build_initial_messages(goal, session)
            iteration = 0
        
        # 执行循环
        while iteration < task_ctx.max_iterations:
            iteration += 1
            
            # 周期性checkpoint
            if iteration % task_ctx.checkpoint_interval == 0:
                await self._save_checkpoint(task_ctx, messages, iteration)
            
            # 决策：下一步动作
            action = await self._decide_next_action(task_ctx, messages)
            
            if action.type == ActionType.COMPLETE:
                return AgentResult(
                    status=AgentStatus.SUCCESS,
                    result=action.result,
                    iterations=iteration
                )
            
            if action.type == ActionType.TOOL_CALL:
                result = await self._execute_tool(action.tool_call)
                messages = self._add_tool_result(messages, result)
                
            if action.type == ActionType.REFLECT:
                # 自我反思，调整策略
                messages = await self._reflect_and_adjust(task_ctx, messages)
            
            if action.type == ActionType.ASK_USER:
                # 需要用户澄清
                return AgentResult(
                    status=AgentStatus.WAITING_INPUT,
                    question=action.question,
                    checkpoint=await self._save_checkpoint(task_ctx, messages, iteration)
                )
        
        return AgentResult(
            status=AgentStatus.MAX_ITERATIONS,
            result="Maximum iterations reached"
        )
    
    async def _decide_next_action(
        self,
        ctx: TaskContext,
        messages: list[dict]
    ) -> AgentAction:
        """
        决策下一步动作
        使用ReAct-style reasoning
        """
        response = await self.loop.provider.chat(
            messages=messages,
            tools=self._get_all_tools(),
            model=self.loop.model,
        )
        
        if response.has_tool_calls:
            return AgentAction(
                type=ActionType.TOOL_CALL,
                tool_call=response.tool_calls[0]
            )
        
        content = response.content or ""
        
        # 检测完成信号
        if self._is_complete_signal(content):
            return AgentAction(type=ActionType.COMPLETE, result=content)
        
        # 检测需要用户输入
        if self._needs_user_input(content):
            return AgentAction(
                type=ActionType.ASK_USER,
                question=self._extract_question(content)
            )
        
        # 默认继续
        return AgentAction(type=ActionType.CONTINUE)


class TaskMemory:
    """
    跨任务记忆系统
    - 自动提取关键信息
    - 向量化存储
    - 语义检索
    """
    
    def __init__(self, workspace: Path, embedding_provider: EmbeddingProvider):
        self.store = VectorStore(workspace / "task_memory")
        self.extractor = InsightExtractor(embedding_provider)
    
    async def record_task_execution(
        self,
        task: TaskPlan,
        execution: PlanExecution
    ) -> None:
        """
        记录任务执行，提取可复用知识
        """
        # 提取洞察
        insights = await self.extractor.extract(task, execution)
        
        # 存储到向量数据库
        for insight in insights:
            await self.store.add(
                text=insight.description,
                embedding=insight.embedding,
                metadata={
                    "task_type": task.goal_type,
                    "tools_used": insight.tools_used,
                    "success": execution.status == ExecutionStatus.COMPLETED,
                    "created_at": now()
                }
            )
    
    async def retrieve_relevant_experience(
        self,
        goal: str,
        k: int = 3
    ) -> list[TaskExperience]:
        """
        检索相关历史经验
        """
        query_embedding = await self.extractor.embed(goal)
        return await self.store.search(query_embedding, k=k)
```

---

## 4. 记忆系统增强

### 4.1 三层记忆架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Enhanced Memory System                   │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Working Mem  │  │ Episodic Mem │  │ Semantic Mem │      │
│  │              │  │              │  │              │      │
│  │ Session      │  │ Task History │  │ Facts/Skills │      │
│  │ Context      │  │ Checkpoints  │  │ Knowledge    │      │
│  │ 10-100 msgs  │  │ SQLite       │  │ Vector DB    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         ↑                  ↑                ↑              │
│    Current Task     Past Experiences    Learned Facts       │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 实现方案

```python
# nanobot/memory/enhanced_memory.py

class EnhancedMemorySystem:
    """
    三层记忆系统
    """
    
    def __init__(self, workspace: Path, provider: EmbeddingProvider):
        # L1: 工作记忆（现有Session扩展）
        self.working = WorkingMemory(
            max_tokens=8000,
            strategy="sliding_window_with_summarization"
        )
        
        # L2: 情景记忆（任务历史）
        self.episodic = EpisodicMemory(
            store_path=workspace / "memory" / "episodic.db"
        )
        
        # L3: 语义记忆（知识库）
        self.semantic = SemanticMemory(
            vector_path=workspace / "memory" / "semantic",
            provider=provider
        )
    
    async def retrieve(
        self,
        query: str,
        context: RetrievalContext
    ) -> RetrievedContext:
        """
        分层检索
        """
        # L1: 从当前会话检索
        working_results = self.working.retrieve(query, k=5)
        
        # L2: 从相似任务检索
        episodic_results = await self.episodic.retrieve(
            query, 
            task_type=context.task_type,
            k=3
        )
        
        # L3: 从知识库检索
        semantic_results = await self.semantic.retrieve(query, k=3)
        
        # 融合排序
        return self._fuse_results(
            working_results, 
            episodic_results, 
            semantic_results
        )
    
    async def consolidate(
        self,
        session: Session
    ) -> None:
        """
        记忆固化：工作记忆 → 情景/语义记忆
        """
        # 提取关键事件
        episodes = await self._extract_episodes(session)
        for ep in episodes:
            await self.episodic.store(ep)
        
        # 提取事实知识
        facts = await self._extract_facts(session)
        for fact in facts:
            await self.semantic.store(fact)
```

---

## 5. 集成架构

### 5.1 完整架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Interface                                  │
│  (CLI / Telegram / Discord / Web / ...)                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Mode Router                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  Intent Classifier: ask | plan | agent | switch                      │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
       │                │                │
       ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────────────────────────────┐
│  ASK Mode    │ │  PLAN Mode   │ │              AGENT Mode                  │
│              │ │              │ │                                          │
│ Quick LLM    │ │ Task Planner │ │  ┌──────────────┐  ┌──────────────┐     │
│ No tools     │ │ User Confirm │ │  │ TaskFlow     │  │ Enhanced     │     │
│ Fast/Cheap   │ │ Step Exec    │ │  │   Engine     │  │   Memory     │     │
└──────────────┘ └──────────────┘ │  └──────────────┘  └──────────────┘     │
                                  │                                          │
                                  │  ┌──────────────┐  ┌──────────────┐     │
                                  │  │ Checkpoint   │  │ Cross-Session│     │
                                  │  │   Store      │  │   Memory     │     │
                                  │  └──────────────┘  └──────────────┘     │
                                  └──────────────────────────────────────────┘
                                                   │
                                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Shared Infrastructure                                │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │ LLM Provider│ │ Tool Registry│ │ Session     │ │ Persistence Layer   │   │
│  │ (Multi)     │ │ (MCP + Native)│ │ Manager     │ │ (SQLite + File)     │   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 配置方案

```json
// ~/.nanobot/config.json
{
  "modes": {
    "default": "ask",
    "auto_detect": true,
    "ask": {
      "model": "openrouter/google/gemma-3-4b-it",
      "max_tokens": 1024,
      "context_window": 10
    },
    "plan": {
      "model": "anthropic/claude-sonnet-4",
      "require_approval": true,
      "max_steps": 20
    },
    "agent": {
      "model": "anthropic/claude-opus-4",
      "max_iterations": 100,
      "checkpoint_interval": 10,
      "auto_save": true
    }
  },
  "memory": {
    "working": {
      "max_messages": 100,
      "consolidation_threshold": 50
    },
    "episodic": {
      "enabled": true,
      "retrieval_k": 3
    },
    "semantic": {
      "enabled": true,
      "embedding_model": "openai/text-embedding-3-small",
      "vector_store": "chroma"  // or "faiss", "qdrant"
    }
  },
  "taskflow": {
    "persistence": "sqlite",
    "checkpoint_enabled": true,
    "max_concurrent_tasks": 5
  }
}
```

---

## 6. 技术方案对比

### 6.1 方案对比表

| 维度 | 方案A: 轻量扩展 | 方案B: 完整重构 | 方案C: 混合架构 |
|------|---------------|---------------|---------------|
| **核心思路** | 在现有架构上叠加mode层 | 完全重新设计核心 | 保留核心，扩展外围 |
| **ASK模式** | ✅ 简单实现 | ✅ 原生支持 | ✅ 简单实现 |
| **PLAN模式** | ⚠️ 基础DAG | ✅ 完整工作流 | ✅ 中等复杂度 |
| **AGENT模式** | ⚠️ 增强loop | ✅ 全新设计 | ✅ 增强loop |
| **记忆系统** | ⚠️ 扩展现有 | ✅ 三层架构 | ✅ 三层架构 |
| **开发周期** | 2-3周 | 6-8周 | 4-5周 |
| **代码增量** | ~2K行 | ~8K行 | ~4K行 |
| **向后兼容** | ✅ 100% | ❌ 需迁移 | ✅ 90% |
| **维护成本** | 低 | 高 | 中 |
| **扩展性** | 中 | 高 | 高 |

### 6.2 推荐方案: C (混合架构)

**选择理由：**
1. **保留核心价值**: nanobot的轻量级特性 (~4K行核心代码)
2. **渐进式演进**: 不破坏现有用户习惯
3. **可控复杂度**: 4-5周开发周期，风险可控
4. **未来扩展**: 为更复杂功能预留接口

---

## 7. 实施路线图

### Phase 1: ASK Mode (Week 1)

```
Day 1-2: Mode Router基础框架
  - 创建 nanobot/modes/ 模块
  - 实现 ModeRouter 类
  - 添加 IntentClassifier

Day 3-4: ASK Mode实现
  - AskModeProcessor
  - Tool-less prompt builder
  - 轻量模型配置

Day 5: 集成与测试
  - 集成到 AgentLoop
  - 单元测试
  - 模式切换测试
```

### Phase 2: PLAN Mode (Week 2-3)

```
Week 2:
  - TaskPlan 数据模型
  - PlanModeProcessor.create_plan()
  - 用户确认流程
  
Week 3:
  - DAG执行引擎
  - Step-by-step执行
  - 进度追踪
  - 暂停/恢复功能
```

### Phase 3: AGENT增强 (Week 4)

```
- Checkpoint/Resume机制
- TaskMemory集成
- 长期运行任务支持
- 错误恢复策略
```

### Phase 4: 记忆系统 (Week 5)

```
- 向量存储集成 (Chroma/Faiss)
- Embedding Provider封装
- 三层记忆实现
- 记忆检索优化
```

---

## 8. 关键设计决策

### 8.1 决策记录

| ID | 决策 | 选项 | 选择 | 理由 |
|----|------|------|------|------|
| ADR-001 | 任务流存储 | SQLite/JSONL/混合 | 混合 | 结构化数据用SQLite，大文本用文件 |
| ADR-002 | 向量数据库 | Chroma/Faiss/Qdrant | Chroma | 轻量、嵌入式、无需外部服务 |
| ADR-003 | 模式切换 | 自动/手动/混合 | 混合 | 默认自动，用户可强制指定 |
| ADR-004 | Checkpoint | 全量/增量 | 增量 | 减少存储，加速恢复 |
| ADR-005 | DAG执行 | 顺序/并行/混合 | 混合 | 按依赖自动决定 |

### 8.2 风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 向量存储增加包体积 | 高 | 高 | 可选依赖，按需安装 |
| 模式误判 | 中 | 中 | 提供显式切换命令 |
| 任务状态不一致 | 高 | 低 | 事务性存储，定期校验 |
| 长期任务内存泄漏 | 中 | 中 | 定期checkpoint，限制并发 |

---

## 9. API设计

### 9.1 CLI扩展

```bash
# 模式切换
nanobot mode ask      # 切换到ASK模式
nanobot mode plan     # 切换到PLAN模式  
nanobot mode agent    # 切换到AGENT模式
nanobot mode auto     # 自动检测模式

# 任务流管理
nanobot task list                    # 列出活跃任务
nanobot task show <task_id>          # 查看任务详情
nanobot task pause <task_id>         # 暂停任务
nanobot task resume <task_id>        # 恢复任务
nanobot task cancel <task_id>        # 取消任务

# 计划操作（PLAN模式）
nanobot plan create "description"    # 创建计划（非交互）
nanobot plan approve <plan_id>       # 批准计划
nanobot plan modify <plan_id>        # 修改计划
```

### 9.2 内部API

```python
# 模式处理接口
class ModeProcessor(ABC):
    @abstractmethod
    async def process(self, ctx: ModeContext) -> ModeResult: ...
    
    @abstractmethod
    def should_handle(self, intent: Intent) -> bool: ...

# 任务流接口
class TaskFlowEngine:
    async def create_task(self, spec: TaskSpec) -> Task: ...
    async def execute_task(self, task_id: str) -> Execution: ...
    async def pause_task(self, task_id: str) -> None: ...
    async def resume_task(self, task_id: str) -> None: ...
    async def get_status(self, task_id: str) -> TaskStatus: ...
```

---

## 10. 总结

### 10.1 预期收益

| 维度 | 当前 | 目标 | 提升 |
|------|------|------|------|
| 响应速度(简单查询) | 3-5s | <1s | 3-5x |
| 复杂任务成功率 | 60% | 85% | 42% |
| 用户控制感 | 低 | 高 | - |
| 长任务支持 | ❌ | ✅ | - |
| 跨会话学习 | ❌ | ✅ | - |

### 10.2 工作量估算

| 模块 | 预估代码量 | 开发时间 | 测试时间 |
|------|-----------|----------|----------|
| Mode System | ~800行 | 1周 | 3天 |
| TaskFlow Engine | ~1500行 | 2周 | 1周 |
| Enhanced Memory | ~1000行 | 1周 | 1周 |
| Integration | ~500行 | 3天 | 3天 |
| Tests & Docs | ~1200行 | - | 并行 |
| **Total** | **~5000行** | **~5周** | **~3周** |

### 10.3 下一步行动

1. **技术验证** (本周)
   - 验证Chroma集成可行性
   - 测试轻量模型在ASK模式的效果
   - 原型验证DAG执行

2. **详细设计** (下周)
   - 数据库schema设计
   - API详细设计
   - 状态机详细设计

3. **开发启动**
   - 按Phase划分开发任务
   - 每Phase完成后进行集成测试

---

*本方案基于nanobot v0.1.4架构评估，实际实施时需根据最新代码调整。*
