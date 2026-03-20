# nanobot 记忆系统实现方案

## 概述

nanobot 采用**三层记忆架构**设计，在保持代码简洁（约150行核心代码）的同时，实现了高效、可靠的对话记忆管理。该系统能够：

- 🧠 **长期记忆**：持久化存储重要事实和用户偏好
- 📝 **历史记录**：可搜索的对话时间线
- ⚡ **工作记忆**：当前对话上下文，支持Prompt缓存优化

---

## 架构设计

### 三层记忆架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         nanobot 三层记忆架构                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Layer 3: 长期记忆 (Long-term)                 │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │  📄 MEMORY.md                                                │   │   │
│  │  │  ┌────────────────────────────────────────────────────────┐ │   │   │
│  │  │  │ • 用户画像 (User Profile)                               │ │   │   │
│  │  │  │ • 偏好设置 (Preferences)                                │ │   │   │
│  │  │  │ • 项目背景 (Project Context)                            │ │   │   │
│  │  │  │ • 重要事实 (Key Facts)                                  │ │   │   │
│  │  │  └────────────────────────────────────────────────────────┘ │   │   │
│  │  │                                                              │   │   │
│  │  │  特点：结构化、持久化、LLM可读写                              │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    ▲                                        │
│                                    │ 定期固化                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Layer 2: 历史记录 (History)                   │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │  📄 HISTORY.md                                               │   │   │
│  │  │  ┌────────────────────────────────────────────────────────┐ │   │   │
│  │  │  │ [2026-03-07 10:30] USER: 询问天气...                     │ │   │   │
│  │  │  │ [2026-03-07 10:31] ASSISTANT: 今天晴天...                │ │   │   │
│  │  │  │ [2026-03-07 10:32] USER: 提醒我买牛奶...                  │ │   │   │
│  │  │  │ [2026-03-07 10:33] ASSISTANT: 已记录提醒 [tools:...]    │ │   │   │
│  │  │  └────────────────────────────────────────────────────────┘ │   │   │
│  │  │                                                              │   │   │
│  │  │  特点：时间戳索引、grep可搜索、追加写入                        │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    ▲                                        │
│                                    │ 触发条件                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Layer 1: 工作记忆 (Working)                   │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │  💬 Session (内存)                                           │   │   │
│  │  │  ┌────────────────────────────────────────────────────────┐ │   │   │
│  │  │  │  • 最近对话消息 (默认窗口: 100条)                        │ │   │   │
│  │  │  │  • Tool Call 结果                                       │ │   │   │
│  │  │  │  • 消息时间戳、工具使用记录                              │ │   │   │
│  │  │  │  • Prompt Caching 优化 (append-only)                    │ │   │   │
│  │  │  └────────────────────────────────────────────────────────┘ │   │   │
│  │  │                                                              │   │   │
│  │  │  特点：高速访问、支持Prompt缓存、自动截断                     │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 系统组件关系图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           nanobot 记忆系统组件                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐              │
│   │  AgentLoop   │────▶│ContextBuilder│────▶│ MemoryStore  │              │
│   │   (loop.py)  │◄────│ (context.py) │◄────│ (memory.py)  │              │
│   └──────────────┘     └──────────────┘     └──────────────┘              │
│          │                    │                    │                       │
│          │                    │                    │                       │
│          ▼                    ▼                    ▼                       │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────┐  │
│   │SessionManager│     │System Prompt │     │   记忆固化 (Consolidation) │  │
│   │(manager.py)  │     │   Builder    │     │                          │  │
│   └──────────────┘     └──────────────┘     │  ┌────────────────────┐  │  │
│          │                                  │  │ 1. 触发条件检查     │  │  │
│          │                                  │  │    (窗口满/命令)   │  │  │
│          ▼                                  │  ├────────────────────┤  │  │
│   ┌──────────────┐                         │  │ 2. LLM调用          │  │  │
│   │  Session     │                         │  │    save_memory工具 │  │  │
│   │  (内存+文件)  │                         │  ├────────────────────┤  │  │
│   └──────────────┘                         │  │ 3. 更新MEMORY.md    │  │  │
│                                            │  │ 4. 追加HISTORY.md   │  │  │
│                                            │  └────────────────────┘  │  │
│                                            └──────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 核心组件详解

### 1. MemoryStore - 记忆存储器

**文件**: `nanobot/agent/memory.py`

```python
class MemoryStore:
    """Two-layer memory: MEMORY.md (long-term facts) + HISTORY.md (grep-searchable log)."""
    
    def __init__(self, workspace: Path):
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "HISTORY.md"
```

#### 职责：
| 方法 | 功能 |
|------|------|
| `read_long_term()` | 读取 MEMORY.md 中的长期记忆 |
| `write_long_term()` | 更新 MEMORY.md |
| `append_history()` | 追加历史记录到 HISTORY.md |
| `get_memory_context()` | 获取系统提示词中的记忆上下文 |
| `consolidate()` | 执行记忆固化（核心方法）|

### 2. Session - 会话对象

**文件**: `nanobot/session/manager.py`

```python
@dataclass
class Session:
    """
    A conversation session.
    
    Important: Messages are append-only for LLM cache efficiency.
    The consolidation process writes summaries to MEMORY.md/HISTORY.md
    but does NOT modify the messages list.
    """
    
    key: str                    # channel:chat_id 格式
    messages: list[dict]        # 消息列表（追加-only）
    created_at: datetime
    updated_at: datetime
    last_consolidated: int      # 已固化的消息数量
```

#### 关键设计：
- **追加-only**: 消息从不删除或修改，仅追加，支持Prompt缓存
- **`last_consolidated`**: 标记已固化的消息边界
- **`get_history()`**: 只返回未固化的消息给LLM

### 3. SessionManager - 会话管理器

**文件**: `nanobot/session/manager.py`

```python
class SessionManager:
    """Manages conversation sessions stored as JSONL files."""
    
    def __init__(self, workspace: Path):
        self.sessions_dir = ensure_dir(workspace / "sessions")
        self._cache: dict[str, Session] = {}
```

#### 存储格式 (JSONL):
```json
{"_type": "metadata", "key": "telegram:123456", "created_at": "2026-03-07T10:00:00", "last_consolidated": 50}
{"role": "user", "content": "你好", "timestamp": "2026-03-07T10:00:00"}
{"role": "assistant", "content": "你好！有什么可以帮助你？", "timestamp": "2026-03-07T10:00:01"}
```

---

## 记忆固化流程

### 触发条件

```
┌─────────────────────────────────────────────────────────────┐
│                     记忆固化触发条件                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  条件1: 自动触发                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  unconsolidated >= memory_window (默认100条)        │   │
│  │  且当前没有正在进行的固化任务                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│  条件2: 手动触发 (/new 命令)                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  用户发送 /new 命令                                  │   │
│  │  归档所有消息后清空会话                              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 固化算法

```python
async def consolidate(self, session, provider, model, *, archive_all=False, memory_window=50):
    """
    记忆固化核心算法
    
    Args:
        archive_all: True=归档所有消息(用于/new命令), False=只归档旧消息
        memory_window: 工作记忆窗口大小
    """
    if archive_all:
        # /new 命令：归档所有消息
        old_messages = session.messages
        keep_count = 0
    else:
        # 自动触发：保留最近一半消息作为工作记忆
        keep_count = memory_window // 2  # 保留50条
        old_messages = session.messages[session.last_consolidated:-keep_count]
    
    # 1. 构建提示词
    prompt = f"""
    ## Current Long-term Memory
    {current_memory}
    
    ## Conversation to Process
    {conversation_lines}
    """
    
    # 2. 调用LLM的save_memory工具
    response = await provider.chat(
        messages=[...],
        tools=[save_memory_tool],  # 强制调用工具
    )
    
    # 3. 更新MEMORY.md（长期记忆）
    self.write_long_term(args["memory_update"])
    
    # 4. 追加HISTORY.md（历史日志）
    self.append_history(args["history_entry"])
    
    # 5. 更新last_consolidated标记
    session.last_consolidated = len(session.messages) - keep_count
```

### 固化工具定义

```python
_SAVE_MEMORY_TOOL = [{
    "type": "function",
    "function": {
        "name": "save_memory",
        "description": "Save the memory consolidation result to persistent storage.",
        "parameters": {
            "type": "object",
            "properties": {
                "history_entry": {
                    "type": "string",
                    "description": "A paragraph summarizing key events/decisions/topics. "
                                   "Start with [YYYY-MM-DD HH:MM]."
                },
                "memory_update": {
                    "type": "string", 
                    "description": "Full updated long-term memory as markdown. "
                                   "Include all existing facts plus new ones."
                },
            },
            "required": ["history_entry", "memory_update"]
        }
    }
}]
```

---

## 文件存储结构

```
~/.nanobot/workspace/                    # 工作空间
├── memory/                               # 记忆目录
│   ├── MEMORY.md                         # 长期记忆（结构化Markdown）
│   └── HISTORY.md                        # 历史记录（时间线日志）
│
├── sessions/                             # 会话目录
│   ├── telegram_123456.jsonl            # Telegram会话
│   ├── discord_789012.jsonl             # Discord会话
│   └── cli_direct.jsonl                 # CLI会话
│
└── AGENTS.md                             # 启动引导文件
```

### MEMORY.md 示例

```markdown
# Long-term Memory

## User Information

- 用户名: Alice
- 职业: 软件工程师
- 所在城市: 北京

## Preferences

- 编程语言偏好: Python, Rust
- 沟通风格: 简洁直接
- 时区: Asia/Shanghai

## Project Context

### nanobot项目
- 角色: 贡献者
- 正在开发: 记忆系统优化
- 截止日期: 2026-03-15

## Important Notes

- 对代码质量要求很高
- 不喜欢冗余的解释
```

### HISTORY.md 示例

```markdown
[2026-03-07 09:30] USER: 帮我查看天气 [tools: web_search]
[2026-03-07 09:31] ASSISTANT: 北京今天晴天，15-22°C

[2026-03-07 10:15] USER: 记录一下我需要买牛奶
[2026-03-07 10:16] ASSISTANT: 已记录提醒事项 [tools: write_file]

[2026-03-07 11:00] USER: /new
[2026-03-07 11:01] ASSISTANT: 新会话已开始，之前的对话已归档
```

---

## 工作流程图解

### 完整对话处理流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         对话处理完整流程                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  用户发送消息                                                                │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 1. 检查命令                                                         │   │
│  │    • /new  → 归档所有记忆，清空会话                                  │   │
│  │    • /stop → 停止当前任务                                           │   │
│  │    • /help → 显示帮助                                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 2. 检查记忆固化条件                                                  │   │
│  │    unconsolidated >= memory_window?                                 │   │
│  │    是 → 异步启动consolidate_task                                     │   │
│  │    否 → 继续                                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 3. 构建上下文 (ContextBuilder)                                       │   │
│  │    ┌─────────────┐                                                  │   │
│  │    │ System Prompt│  Identity + AGENTS.md + MEMORY.md + Skills     │   │
│  │    ├─────────────┤                                                  │   │
│  │    │   History    │  session.get_history() → 未固化的消息            │   │
│  │    ├─────────────┤                                                  │   │
│  │    │Runtime Context│ 当前时间、频道信息                              │   │
│  │    ├─────────────┤                                                  │   │
│  │    │User Message  │ 当前用户输入                                    │   │
│  │    └─────────────┘                                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 4. LLM迭代循环 (AgentLoop._run_agent_loop)                           │   │
│  │    while iteration < max_iterations:                                │   │
│  │        response = provider.chat(messages, tools)                    │   │
│  │        if has_tool_calls:                                           │   │
│  │            result = execute_tools(response.tool_calls)              │   │
│  │            messages.append(result)                                  │   │
│  │        else:                                                        │   │
│  │            break  # 得到最终回复                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 5. 保存会话                                                          │   │
│  │    • _save_turn(): 追加新消息到session.messages                      │   │
│  │    • session_manager.save(): 持久化到JSONL文件                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                     │
│       ▼                                                                     │
│  发送回复给用户                                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 关键设计决策

### 1. 为什么采用三层架构？

| 层级 | 解决的问题 | 设计理由 |
|------|-----------|----------|
| **工作记忆** | LLM上下文窗口限制 | 只保留最近消息，控制token消耗 |
| **历史记录** | 可追溯性需求 | grep可搜索，便于审计和查找 |
| **长期记忆** | 跨会话记忆持久化 | 结构化存储，LLM可直接使用 |

### 2. 为什么消息是追加-only？

```
┌─────────────────────────────────────────────────────────────┐
│                    Prompt Caching 优势                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  传统方式 (修改消息列表)        追加-only方式                  │
│  ┌──────────────────────┐      ┌──────────────────────┐    │
│  │ Message 1            │      │ Message 1            │    │
│  │ Message 2            │      │ Message 2            │    │
│  │ Message 3  ◄── 删除   │      │ Message 3            │    │
│  │ Message 4  ◄── 删除   │      │ Message 4            │    │
│  │ Message 5            │      │ Message 5            │    │
│  │ Message 6 (new)      │      │ Message 6 (new)      │    │
│  └──────────────────────┘      └──────────────────────┘    │
│                                                             │
│  ❌ 缓存失效，全部重新计算       ✅ 缓存有效，只计算新消息      │
│  ❌ 增加token成本              ✅ 降低API成本               │
│  ❌ 增加延迟                   ✅ 更快响应                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3. 为什么使用LLM进行记忆固化？

- **智能摘要**：比简单的文本截断更能保留关键信息
- **结构化输出**：自动整理成Markdown格式
- **事实提取**：从对话中提取重要事实更新MEMORY.md
- **灵活性**：可根据内容类型自适应处理

### 4. 并发安全设计

```python
class AgentLoop:
    def __init__(self):
        self._consolidating: set[str] = set()          # 正在固化的会话
        self._consolidation_locks: dict[str, Lock] = {} # 每会话锁
        self._processing_lock = asyncio.Lock()         # 全局处理锁
```

- **每会话锁**: 不同会话可并行处理
- **全局锁**: 保证单个会话消息处理串行
- **`_consolidating`集合**: 防止重复触发

---

## 配置选项

```json
{
  "agents": {
    "defaults": {
      "memoryWindow": 100,      // 工作记忆窗口大小
      "maxIterations": 40       // 最大工具调用迭代次数
    }
  }
}
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `memoryWindow` | 100 | 工作记忆保留的消息数，超过则触发固化 |
| `maxIterations` | 40 | 单次对话最大工具调用次数 |

---

## 总结

nanobot的记忆系统通过**三层架构**和**智能固化**机制，在保持代码简洁的同时实现了：

1. ✅ **高效**: Prompt缓存友好，API成本低
2. ✅ **可靠**: 文件持久化，崩溃恢复安全
3. ✅ **可扩展**: 模块化设计，易于扩展
4. ✅ **智能**: LLM驱动的记忆摘要和事实提取

整个记忆系统核心代码仅约**150行**，体现了nanobot" ultra-lightweight"的设计理念。

---

*文档生成时间: 2026-03-07*
