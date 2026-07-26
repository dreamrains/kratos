"""全量回归测试"""
import sys
import os
import json
import shutil

sys.stdout.reconfigure(encoding="utf-8")

PASSED = 0
FAILED = 0
ISSUES = []


def check(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  [PASS] {name}")
    else:
        FAILED += 1
        msg = f"  [FAIL] {name}: {detail}"
        print(msg)
        ISSUES.append(msg)


print("=" * 60)
print("全量回归测试")
print("=" * 60)

# ======== 1. 意图分类 ========
print("\n--- 1. 意图分类 ---")
from data_agent.agent.prompts import _classify_task

cases = [
    ("你好", "conversation"), ("hello", "conversation"), ("谢谢", "conversation"),
    ("好的", "conversation"), ("什么是同比和环比", "conversation"),
    ("解释一下什么是回归分析", "conversation"), ("介绍一下RFM分析方法", "conversation"),
    ("分析一下销售趋势", "guidance"), ("帮我看看这数据", "guidance"),
    ("预测下季度销售", "guidance"), ("出个报告", "analysis"), ("完整分析", "analysis"),
    ("帮我算一下总销售额", "quick"), ("导出数据为csv", "quick"),
    ("按月分组汇总", "quick"), ("排序", "quick"),
]
for inp, expected in cases:
    result = _classify_task(inp)
    check(f'"{inp}" -> {expected}', result == expected, f"got={result}")

# ======== 2. 领域知识 ========
print("\n--- 2. 领域知识 suggested_analyses ---")
from data_agent.knowledge.domain import DomainKnowledge

d = DomainKnowledge()
ecom = d._ecommerce_template()
game = d._gaming_template()
check("电商模板有 suggested_analyses", "suggested_analyses" in ecom and len(ecom["suggested_analyses"]) >= 3)
check("游戏模板有 suggested_analyses", "suggested_analyses" in game and len(game["suggested_analyses"]) >= 3)
d.set_domain("ecommerce")
prompt_text = d.get_for_prompt()
check("电商 prompt 包含 suggested_analyses", "suggested_analyses" in prompt_text)

# ======== 3. 压缩边界安全 ========
print("\n--- 3. 压缩边界安全 ---")
from data_agent.agent.compact import _find_safe_boundary

msgs = [
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "hello"},
    {"role": "user", "content": "analyze"},
    {"role": "assistant", "content": "done"},
    {"role": "user", "content": "next"},
]
idx = _find_safe_boundary(msgs, 2)
check("正常分割点", idx == 3, f"got={idx}")

msgs = [
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "hello"},
    {"role": "user", "content": "load"},
    {"role": "assistant", "content": "", "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "load_data", "arguments": ""}}]},
    {"role": "tool", "tool_call_id": "tc1", "content": "loaded"},
]
idx = _find_safe_boundary(msgs, 1)
recent = msgs[idx:]
has_tool = any(m.get("role") == "tool" for m in recent)
has_tc = any(m.get("role") == "assistant" and m.get("tool_calls") for m in recent)
check("tool result 边界安全", not has_tool or has_tc, f"split={idx}")

from data_agent.agent.execution_control import ToolExecutionBudget, TurnExecutionState

budget_state = TurnExecutionState(ToolExecutionBudget(
    token_budget=1000,
    synthesis_reserve_tokens=200,
    audit_reserve_tokens=100,
    revision_reserve_tokens=100,
))
budget_state.record_token_usage(600, phase="exploration")
check(
    "探索预算不占用最终审计储备",
    budget_state.exploration_budget_exhausted and budget_state.can_run_phase("audit"),
)

# ======== 4. JSONL 持久化 ========
print("\n--- 4. JSONL 持久化 ---")
from data_agent.config import get_config
from data_agent.session.history import (
    push_message, push_messages, save_session, load_session, _session_dir,
)

cfg = get_config()
test_sid = "_regr_" + str(id([]))[-6:]
sdir = _session_dir(test_sid)

push_message(test_sid, {"role": "user", "content": "hello"})
push_message(test_sid, {"role": "assistant", "content": "hi"})
check("push_message 创建 JSONL", (sdir / "conversation.jsonl").exists())

data = load_session(test_sid)
check("load_session 仅 JSONL", data is not None and data["message_count"] == 2, f"got={data}")

save_session(data["messages"], test_sid)
check("save_session 清除 JSONL", not (sdir / "conversation.jsonl").exists() and (sdir / "conversation.json").exists())

push_message(test_sid, {"role": "user", "content": "q2"})
data = load_session(test_sid)
check("JSONL 追加到 JSON", data is not None and data["message_count"] == 3)

save_session(data["messages"], test_sid, data_file="test.csv")
data2 = load_session(test_sid)
check("完整保存后重载一致", data2["message_count"] == 3 and data2["data_file"] == "test.csv")

empty_sid = "_regr_empty_" + str(id([]))[-6:]
check("空目录返回 None", load_session(empty_sid) is None)

shutil.rmtree(sdir, ignore_errors=True)

# ======== 5. 会话分支 ========
print("\n--- 5. 会话分支 ---")
from data_agent.session.history import branch_session, list_branches

parent_sid = "_regr_par_" + str(id([]))[-6:]
msgs = [{"role": "user", "content": "load"}, {"role": "assistant", "content": "done"}]
save_session(msgs, parent_sid, data_file="sales.csv")

result = branch_session(parent_sid, "test_branch")
check("创建分支成功", result["success"] and result["message_count"] == 2, str(result))

branch_data = load_session(result["session_id"])
check("分支数据正确", branch_data["message_count"] == 2 and branch_data.get("data_file") == "sales.csv")

branches = list_branches(parent_sid)
check("list_branches 返回正确", len(branches) == 1 and branches[0]["branch_name"] == "test_branch")

branch_msgs = branch_data["messages"] + [{"role": "user", "content": "more"}]
save_session(branch_msgs, result["session_id"])
parent = load_session(parent_sid)
check("分支独立", parent["message_count"] == 2)

check("分支不存在会话", not branch_session("nonexistent", "x")["success"])

shutil.rmtree(_session_dir(parent_sid), ignore_errors=True)
shutil.rmtree(_session_dir(result["session_id"]), ignore_errors=True)

# ======== 6. 静默探查 ========
# NOTE: This section requires test data files in reference/workspace/
# which may not exist in all environments. Skip gracefully.
print("\n--- 6. 静默探查（紧凑模式）---")
base = "D:/Project/Daily/data-agent/reference/workspace"
if os.path.isdir(base):
    from data_agent.tools.data_io import load_data
    from data_agent.session.workspace import workspace
    workspace._datasets.clear()

    result = load_data(os.path.join(base, "test_sales.csv"), name="test_sales")
    check("CSV data_profile", "[data_profile]" in result)
    if "[data_profile]" in result:
        profile = json.loads(result[result.index("[data_profile]") + len("[data_profile]"):result.index("[/data_profile]")].strip())
        check("CSV profile 有效", "shape" in profile and "readiness" in profile)

    workspace._datasets.clear()
    if os.path.exists(os.path.join(base, "内购数据.xlsx")):
        result = load_data(os.path.join(base, "内购数据.xlsx"), name="purchase")
        check("Excel data_profile", "[data_profile]" in result)
        if "[data_profile]" in result:
            profile = json.loads(result[result.index("[data_profile]") + len("[data_profile]"):result.index("[/data_profile]")].strip())
            check("Excel 紧凑模式有 summary", "summary" in profile)
else:
    print("  [SKIP] 测试数据文件不存在，跳过静默探查测试")

if os.path.isdir(base):
    r3 = load_data(os.path.join(base, "banner汇总数据.xlsx"), name="banner")
    check("多文件各自保留 profile", all("[data_profile]" in r for r in [r1, r2, r3]))

    workspace._datasets.clear()
    r = load_data("nonexistent.csv", name="bad")
    check("错误文件无 profile", "[data_profile]" not in r and "Error" in r)

    workspace._datasets.clear()

# ======== 7. Prompt 构建 ========
print("\n--- 7. Prompt 构建 ---")
from data_agent.agent.prompts import build_system_prompt

p = build_system_prompt(tool_list="tools", session_context="- main: 100 rows", user_input="你好")
check("CONVERSATION 无工具有上下文", "可用工具：无" in p and "100 rows" in p)

p = build_system_prompt(tool_list="tools", user_input="导出数据为csv")
check("QUICK 有工具", "数据变换" in p or "transform_data" in p)

p = build_system_prompt(
    tool_list="tools", domain_knowledge="<domain>e</domain>",
    experience_log="<exp>x</exp>", session_context="- main: 10 rows x 3 cols",
    user_input="分析一下销售趋势为什么下降",
)
check("ANALYSIS 注入全部上下文", "<domain>e</domain>" in p and "<exp>x</exp>" in p and "分析策略表" in p)

p = build_system_prompt(tool_list="tools", session_context="- main: 10 rows x 3 cols", user_input="出个完整分析报告")
check("REPORT 含分析引擎", "分析策略表" in p and "comprehensive_report" in p)

# ======== 8. 启动恢复 & 命令 ========
print("\n--- 8. 启动恢复 & 命令 ---")
from data_agent.agent.repl import _format_recent_sessions
output = _format_recent_sessions([
    {"session_id": "a", "saved_at": "2026-04-28 14:30:00", "summary": "test", "object_name": "obj", "message_count": 5},
])
check("_format_recent_sessions", "test" in output and "obj" in output)
check("空会话列表", _format_recent_sessions([]) == "")

# ======== 9. 编译 & 导入 ========
print("\n--- 9. 编译 & 导入 ---")
import py_compile

all_files_ok = True
for f in [
    "src/data_agent/agent/prompts.py",
    "src/data_agent/agent/loop.py",
    "src/data_agent/agent/repl.py",
    "src/data_agent/agent/compact.py",
    "src/data_agent/session/history.py",
    "src/data_agent/tools/data_io.py",
    "src/data_agent/knowledge/domain.py",
    "src/data_agent/tools/data_understand.py",
]:
    try:
        py_compile.compile(f, doraise=True)
    except py_compile.PyCompileError:
        all_files_ok = False
check("全部文件编译通过", all_files_ok)

# ======== 汇总 ========
print()
print("=" * 60)
print(f"回归测试完成: {PASSED} passed, {FAILED} failed")
if ISSUES:
    print("失败项:")
    for i in ISSUES:
        print(i)
print("=" * 60)
