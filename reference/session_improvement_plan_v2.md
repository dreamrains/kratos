# 会话与对象系统改进方案 v2

## 背景

基于 v1 方案的讨论，确认以下设计决策：

1. **知识归属原则**：知识先落会话层，绑定对象时提升到对象层，换绑时跟随会话迁移
2. **Web GUI 暂停**：当前 FastAPI + React 方案暂停，未来迁移到 Flask + HTMX
3. **优先级**：CLI 核心功能优先，所有逻辑写成纯函数供 CLI 和 Web 共用

---

## 一、三层知识架构改造

### 当前结构（两层）

```
全局知识 project/knowledge/         ← 所有会话可见
对象知识 objects/{name}/knowledge/  ← 绑定该对象时可见
```

### 改造后结构（三层）

```
全局知识 project/knowledge/                          ← 始终可见
对象知识 objects/{name}/knowledge/                   ← 绑定该对象时可见
会话知识 sessions/{id}/knowledge/                    ← 该会话始终可见（新增）
```

### 知识流向

```
生成知识 → 写入 sessions/{id}/knowledge/（会话层）
绑定对象 → promote_session_knowledge() 合并到 objects/{name}/knowledge/
换绑对象 → migrate_session_knowledge() 从旧对象迁移到新对象
解绑     → 知识留在对象中，会话层保留副本
```

### 知识条目溯源

每条知识条目增加 `source_session_id` 字段，用于换绑时精确迁移：

```yaml
- id: exp_abc123
  pattern: "..."
  source_session_id: "sess_xyz"  # 新增
```

### 知识可见性（agent prompt 构建）

```
active view = 全局知识 ∪ 当前对象知识 ∪ 当前会话知识
```

---

## 二、动态绑定设计

### 生命周期

```
创建会话（无对象）→ 自由分析
  → /bind <object>   绑定到对象（会话知识提升到对象）
  → /unbind          解绑回自由状态
  → /bind <other>    换绑（先迁移知识，再绑定新对象）
```

### 存储变更

- `sessions/{id}/meta.json` 新增 `object_name` 字段
- `sessions/{id}/knowledge/` 新增会话级知识目录
- `objects/{name}/meta.yaml` 的 `sessions` 列表（已有）

### 绑定流程

```
bind(session_id, object_name):
  1. 读取 session meta → 获取当前 object_name（可能为空）
  2. 如果已有绑定 → 先执行迁移 migrate_session_knowledge()
  3. promote_session_knowledge(session_id → object_name)
  4. object_manager.bind_session(object_name, session_id)
  5. update_session_meta(session_id, {object_name: name})
  6. workspace.set_object(name) + set_active_object(name)
  7. invalidate_prompt_cache()
```

---

## 三、文件改动清单

### 3.1 `session/history.py` — 元数据增强 + 会话知识路径

**新增函数：**
- `session_knowledge_dir(session_id)` → 返回 `sessions/{id}/knowledge/` 路径
- `update_session_meta(session_id, updates)` → 原子更新 meta.json
- `bind_session_to_object(session_id, object_name)` → 完整绑定流程
- `unbind_session_from_object(session_id)` → 完整解绑流程

**修改函数：**
- `list_sessions()` → 返回 `object_name`，支持按对象过滤
- `save_session()` → meta.json 包含 `object_name`

### 3.2 `knowledge/experience.py` — 会话级经验 + 溯源

**修改：**
- `add_draft()` → 新增 `session_id` 参数，知识先写会话层，条目加 `source_session_id`
- `confirm/deprecate/reinforce` → 支持在会话层操作
- `get_for_prompt()` → 三层合并：全局 ∪ 对象 ∪ 会话
- `get_merged_entries()` → 三层合并
- 新增 `promote_to_object(session_id, object_name)` → 将会话经验提升到对象
- 新增 `migrate_between_objects(session_id, from_obj, to_obj)` → 对象间迁移

### 3.3 `knowledge/domain.py` — 会话级领域知识

**修改：**
- `get_merged()` / `get_for_prompt()` → 三层合并
- 新增会话级领域知识读写
- 新增 `promote_to_object()` / `migrate_between_objects()`

### 3.4 `knowledge/rules.py` — 会话级规则

**修改：**
- `get_rules_for_prompt()` → 三层合并
- 新增会话级规则读写
- 新增 `promote_to_object()` / `migrate_between_objects()`

### 3.5 `object_manager.py` — 知识迁移接口

**新增：**
- `extract_session_knowledge(name, session_id)` → 从对象中提取指定会话的知识
- `remove_session_knowledge(name, session_id)` → 从对象中移除指定会话的知识

### 3.6 `agent/loop.py` — 对象上下文恢复 + 三层合并

**新增方法：**
- `restore_object_context()` → 从 meta.json 恢复对象绑定

**修改方法：**
- `_build_system_prompt()` → 三层知识合并
- `_build_session_meta()` → 已有 object_name（确认保留）
- `__init__()` → 对象绑定后不再直接操作 workspace，改用统一接口

### 3.7 `agent/repl.py` — CLI 命令

**新增命令：**
- `/bind <object>` → 绑定当前会话到对象
- `/unbind` → 解绑当前会话

**修改命令：**
- `/resume` → 恢复后调用 `restore_object_context()`
- `/object switch` → 改用 `bind_session_to_object()`
- `/inbox` → 改用 `unbind_session_from_object()`

### 3.8 `tools/knowledge_tools.py` — 工具适配

**修改：**
- `set_active_object()` → 同时更新会话 meta
- 各知识工具 → 支持三层可见性

---

## 四、API 预留（P1，暂不实现路由）

```python
# 以下函数签名供未来 Flask 路由直接调用

# session/history.py
def bind_session_to_object(session_id: str, object_name: str) -> dict: ...
def unbind_session_from_object(session_id: str) -> dict: ...
def list_sessions(object_name: str = "") -> list[dict]: ...

# knowledge/*.py
def promote_session_knowledge(session_id: str, object_name: str) -> dict: ...
def migrate_session_knowledge(session_id: str, from_obj: str, to_obj: str) -> dict: ...

# 未来 Flask 路由只是薄壳：
# @app.route("/api/sessions/<id>/bind", methods=["POST"])
# def bind(session_id):
#     return jsonify(bind_session_to_object(session_id, request.json["object_name"]))
```

---

## 五、验证方案

1. 创建无对象会话 → 分析数据 → `/bind <object>` → 检查会话知识已提升到对象
2. 已绑定对象 A → `/bind <object_B>` → 检查知识从 A 迁移到 B，A 中已无该会话的知识
3. `/unbind` → 检查 meta.json object_name 为空，对象 sessions 列表不含该会话
4. `/resume` → 检查对象上下文正确恢复（workspace.active_object + 知识可见性）
5. `/sessions` → 返回包含 object_name 字段
6. 三层知识可见性：全局 + 对象 + 会话知识同时出现在 agent prompt 中
