# 会话与对象系统综合改进方案

## Context

当前会话系统与"对象"系统存在多层面问题：
1. "对象"命名模糊，实际是"分析项目/分析空间"的概念
2. 会话与对象的绑定关系：创建时固定，不支持动态绑定/解绑/换绑
3. 恢复会话时不恢复对象上下文（workspace、知识系统）
4. 会话列表不支持按对象过滤，不返回完整元数据
5. Workspace 全局单例在 Web 多会话场景有冲突风险
6. Web 层对象切换未调用 `bind_session()`

---

## 一、概念重新定义

### 当前概念层次

```
Data Agent 实例
  └── Project（全局：project/ 目录）
        ├── 全局知识（project_rules, domain_knowledge, experience_log）
        ├── Objects/（对象容器，各自有独立知识和数据）
        ├── Sessions/（会话，可绑定到某个 Object 或自由状态）
        ├── Skills/
        └── inbox/（未归类的数据文件）
```

### 概念分析

当前 "Object" 实际承担的角色：

| 功能 | 说明 |
|------|------|
| 独立数据空间 | 每个对象有自己的 `data/` 目录 |
| 独立知识库 | 对象级 project_rules / domain_knowledge / experience_log |
| 会话组织 | 对象可关联多个会话 |
| 数据来源 | inbox 文件可迁移到对象 |

**结论：Object 实质是"分析项目"（Analysis Project），建议保持内部命名 "object" 不变（避免大范围重命名），但在用户侧 UI 和 API 文档中使用"项目"表述。** 本次不重命名代码，聚焦功能完善。

---

## 二、动态绑定设计

### 生命周期

```
1. 创建会话（无对象）→ 自由探索（inbox 模式）
2. 发现有价值 → 绑定到对象 A（更新 meta.json + 对象 meta.yaml）
3. 后续换绑到对象 B（先从 A unbind，再 bind B）
4. 或解绑回到自由状态（从对象 unind，meta.json 置空）
```

### 存储设计

**只改元数据，不搬文件**：

- `sessions/{id}/meta.json` 的 `object_name` 字段：当前绑定的对象名
- `objects/{name}/meta.yaml` 的 `sessions` 列表：关联的 session_id 数组

绑定/解绑操作 = 同时更新这两处。

---

## 三、改动清单

### 3.1 `session/history.py` — 元数据增强

**改 A**：`list_sessions()` 返回 object_name，支持按对象过滤

```python
def list_sessions(object_name: str = "") -> list[dict]:
    # 返回新增 object_name 字段
    # 支持 object_name 参数过滤（空字符串=全部）
```

**改 B**：新增 `update_session_meta()` 函数

```python
def update_session_meta(session_id: str, updates: dict) -> bool:
    """原子更新会话元数据。用于动态绑定/解绑对象。"""
```

### 3.2 `agent/loop.py` — 对象上下文恢复

**改 C**：新增 `restore_object_context()` 方法

从 meta.json 读取 object_name → 调用 `workspace.set_object()` + `set_active_object()` + 标记 prompt 缓存失效。

```python
def restore_object_context(self) -> None:
    """恢复会话的对象绑定和知识上下文。"""
    # 1. 从 meta.json 读 object_name
    # 2. workspace.set_object(obj)
    # 3. set_active_object(obj)
    # 4. self._prompt_cache_dirty = True
```

### 3.3 `web/routes/sessions.py` — 会话 API 增强

**改 D**：`GET /api/sessions` 支持按对象过滤

```python
@router.get("/sessions")
async def get_sessions(object_name: str = ""):
    return list_sessions(object_name=object_name)
```

**改 E**：新增 `PATCH /api/sessions/{id}` 动态绑定/解绑

```python
class SessionUpdateRequest(BaseModel):
    object_name: Optional[str] = None  # None=不改, ""=解绑, "name"=绑定

@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, body: SessionUpdateRequest):
    # 绑定：bind_session() + update_session_meta(object_name=name)
    # 解绑：unbind_session() + update_session_meta(object_name=None)
    # 换绑：先解绑旧对象，再绑定新对象
```

**改 F**：新增 `POST /api/sessions/{id}/restore` 恢复会话上下文

```python
@router.post("/sessions/{session_id}/restore")
async def restore_session(session_id: str, request: Request):
    # 创建 AgentLoop → 加载消息 → restore_object_context()
    # 返回恢复的会话信息（消息数、对象名、数据集等）
```

### 3.4 `web/schemas.py` — 新增请求模型

```python
class SessionUpdateRequest(BaseModel):
    object_name: Optional[str] = None
```

### 3.5 `web/agent_manager.py` — 创建时自动恢复

`get_or_create()` 中，如果 session_id 已存在于磁盘，自动调用 `restore_object_context()`。

### 3.6 `web/routes/chat.py` — resume 时同步对象

`POST /api/chat` 的 `resume_session_id` 逻辑改为调用 `restore_object_context()`。

### 3.7 `repl.py` — CLI resume 恢复对象

`cmd_resume()` 在恢复消息后调用 `loop.restore_object_context()`。

### 3.8 `web/routes/objects.py` — 对象切换时绑定会话

`POST /api/objects/switch` 增加 `bind_session()` 调用 + 更新 session meta。

---

## 四、文件清单

| 文件 | 改动 |
|------|------|
| `src/data_agent/session/history.py` | list_sessions 加过滤 + object_name，新增 update_session_meta |
| `src/data_agent/agent/loop.py` | 新增 restore_object_context() |
| `src/data_agent/web/routes/sessions.py` | GET 过滤 + PATCH 绑定 + POST 恢复 |
| `src/data_agent/web/schemas.py` | 新增 SessionUpdateRequest |
| `src/data_agent/web/agent_manager.py` | get_or_create 自动恢复对象上下文 |
| `src/data_agent/web/routes/chat.py` | resume 调用 restore_object_context |
| `src/data_agent/web/routes/objects.py` | switch 时 bind_session + 更新 session meta |
| `src/data_agent/agent/repl.py` | cmd_resume 增加对象恢复 |
| `tests/test_full_system.py` | 新增会话管理测试用例 |

共 **9 个文件**（8 个修改 + 测试补充）。

---

## 五、验证方案

1. 创建无对象会话 → 发消息 → `PATCH` 绑定到对象 → 检查 meta.json 和对象 meta.yaml
2. 已绑定会话 → `PATCH` 解绑 → 检查 object_name 为 null，对象 sessions 列表不含该会话
3. 已绑定会话 → `PATCH` 换绑另一对象 → 检查旧对象 sessions 不含、新对象 sessions 包含
4. `GET /api/sessions?object_name=xxx` → 只返回匹配的会话
5. `GET /api/sessions` → 返回包含 object_name 字段
6. `POST /api/sessions/{id}/restore` → 恢复后 workspace.active_object 正确
7. CLI `/resume` → 恢复后对象上下文正确
8. 运行全系统测试确认无回归
