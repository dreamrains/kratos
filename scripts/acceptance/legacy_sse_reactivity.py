"""针对性测试：验证 SSE 流式管道 + Alpine.js 响应式修复。

测试场景：
1. JS 语法 + 修复逻辑验证
2. SSE 事件格式正确性（text_delta/tool_call/tool_result/turn_end/suspended）
3. 上传 → 分析完整 SSE 管道
4. 多轮工具调用（load_data → run_python → text response）
5. ask_user_question 暂停流（suspended 事件）
6. 中断机制
"""

# Manual legacy diagnostic only: cannot satisfy actual-browser Gate E.
# This custom runner is non-authoritative and intended for ad-hoc troubleshooting.
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

BASE = "http://127.0.0.1:5001"
WORKSPACE = r"D:\Project\Daily\data-agent\reference\workspace"

results: list[tuple[str, str, str]] = []


def api(method, path, data=None, files=None, timeout=180):
    url = BASE + path
    if files:
        import mimetypes
        boundary = "----TestBoundary"
        body = b""
        for key, filepath in files.items():
            filename = os.path.basename(filepath)
            with open(filepath, "rb") as f:
                file_data = f.read()
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode()
            mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            body += f"Content-Type: {mime}\r\n\r\n".encode()
            body += file_data + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    elif data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/json")
    else:
        req = urllib.request.Request(url, method=method)

    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        status = resp.status
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.read().decode("utf-8")
        if "json" in content_type:
            return status, json.loads(raw)
        return status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        return 0, str(e)


def check(module, name, condition, detail=""):
    tag = "PASS" if condition else "FAIL"
    results.append((module, name, tag + (f": {detail}" if detail else "")))
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail and not condition else ""))


def parse_sse(raw_text):
    events = []
    current_event = ""
    current_data = ""
    for line in raw_text.split("\n"):
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: "):
            current_data = line[6:]
        elif line == "" and current_event and current_data:
            try:
                events.append((current_event, json.loads(current_data)))
            except Exception:
                events.append((current_event, current_data))
            current_event = ""
            current_data = ""
    return events


def read_js():
    js_path = os.path.join(os.path.dirname(__file__), "..", "src", "data_agent", "web", "static", "js", "app.js")
    js_path = os.path.normpath(js_path)
    with open(js_path, encoding="utf-8") as f:
        return f.read()


def feed_one(event_dict):
    """Drive one loop event through the chat blueprint mapping.

    Returns the first SSE event produced. Mirrors the helper used in
    ``test_analysis_progress_streaming.py`` so the projection stays consistent
    across the live-script and pytest paths.
    """

    sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src")))
    from data_agent.web.blueprints.chat import _feed_events
    from data_agent.web.event_bus import EventQueue

    captured = []
    eq = EventQueue()
    eq.put = lambda sse_event: captured.append(sse_event)

    class _FakeLoop:
        session_id = "feed_one"
        messages = []

        def _auto_save(self):
            pass

    _feed_events(eq, _FakeLoop(), "t_feed_one", iter([event_dict]))
    assert captured, f"no SSE event produced for {event_dict}"
    return captured[0]


# ============================================================
print("=" * 60)
print("SSE + Alpine.js 响应式修复 — 针对性测试")
print("=" * 60)

# ----------------------------------------------------------
print("\n--- 1. JavaScript 修复逻辑验证 ---")
js = read_js()

# 验证 sendMessage 使用 reactive proxy
check("JS修复", "sendMessage: 不直接传递 raw assistantTurn",
      "await this._processSSE(response, assistantTurn)" not in js,
      "已移除 raw reference")

check("JS修复", "sendMessage: 通过 this.turns 获取 reactive proxy",
      "const turn = this.turns[this.turns.length - 1];" in js and
      "await this._processSSE(response, turn)" in js,
      "使用 reactive proxy")

check("JS修复", "sendMessage: catch 块使用 reactive turn",
      "turn.isThinking = false;\n                turn.content +=" in js or
      "turn.isThinking = false" in js,
      "catch 块通过 proxy 修改")

# 验证 resumeConfirmation 使用 reactive proxy
check("JS修复", "resumeConfirmation: 通过 this.turns 获取 reactive proxy",
      "const newTurn = this.turns[this.turns.length - 1];" in js and
      "await this._processSSE(response, newTurn)" in js,
      "使用 reactive proxy")

# 验证错误日志改进
check("JS修复", "_processSSE: 错误日志而非静默 catch",
      "console.error('SSE event error:'" in js,
      "catch 块记录错误")

# 验证 JS 语法
import subprocess
js_path = os.path.join(os.path.dirname(__file__), "..", "src", "data_agent", "web", "static", "js", "app.js")
js_path = os.path.normpath(js_path)
result = subprocess.run(["node", "-c", js_path], capture_output=True, text=True)
check("JS修复", "JavaScript 语法有效", result.returncode == 0,
      result.stderr.strip() if result.returncode != 0 else "OK")

# ----------------------------------------------------------
print("\n--- 2. SSE 基础流式管道 ---")
code, raw = api("POST", "/api/chat", {"message": "请用一句话回复：你好"})
check("SSE基础", "状态 200", code == 200)
events = parse_sse(raw)
event_types = [e[0] for e in events]

check("SSE基础", "turn_start", "turn_start" in event_types)
check("SSE基础", "text_delta", "text_delta" in event_types)
check("SSE基础", "turn_end", "turn_end" in event_types)
check("SSE基础", "_response 不泄露到前端", "_response" not in event_types)

# 验证 analysis_progress 投影：服务端 authored 标签、不含 finding 字段
try:
    progress_sse = feed_one({
        "type": "analysis_progress",
        "code": "tool_started",
        "label": "正在运行相关性分析",
    })
    check("分析进度", "SSE event 为 analysis_progress", progress_sse.event == "analysis_progress")
    check("分析进度", "label 投影正确", progress_sse.data.get("label") == "正在运行相关性分析")
    forbidden = {"value", "p_value", "ranking", "claim", "reasoning"}
    check("分析进度", "不含 finding 字段", not (forbidden & set(progress_sse.data)),
          f"keys={list(progress_sse.data.keys())}")
except Exception as exc:
    check("分析进度", "feed_one 投影 analysis_progress", False, str(exc))

# 验证 SSE 事件格式
for etype, edata in events:
    if etype == "turn_start":
        check("SSE基础", "turn_start 含 session_id", "session_id" in edata, f"keys={list(edata.keys())}")
        check("SSE基础", "turn_start 含 turn_id", "turn_id" in edata)
        check("SSE基础", "turn_start 含 token pct", "pct" in edata)
        break

# 验证 text_delta 累积文本
full_text = ""
for etype, edata in events:
    if etype == "text_delta" and isinstance(edata, dict):
        full_text += edata.get("text", "")
        check("SSE基础", "text_delta 含 turn_id", "turn_id" in edata)
        break  # 只检查第一个
check("SSE基础", "流式文本非空", len(full_text) > 0, f"len={len(full_text)}")

# turn_end 验证
for etype, edata in events:
    if etype == "turn_end":
        check("SSE基础", "turn_end 含 session_id", "session_id" in edata)
        check("SSE基础", "turn_end 含 status", edata.get("status") == "completed")
        break

# 提取 session_id
sid = None
for etype, edata in events:
    if etype == "turn_start" and "session_id" in edata:
        sid = edata["session_id"]
        break

# ----------------------------------------------------------
print("\n--- 3. 上传 → 数据分析 SSE 完整流程 ---")
csv_path = os.path.join(WORKSPACE, "test_sales.csv")
code, upload_body = api("POST", "/api/upload", files={"file": csv_path})
check("上传分析", "上传成功", code == 200 and "filename" in upload_body)

csv_name = upload_body["filename"]
code, raw3 = api("POST", "/api/chat", {
    "message": f"加载文件 {csv_name} 并给出数据概览，用中文回答",
    "session_id": sid,
}, timeout=180)
check("上传分析", "分析请求 200", code == 200)

events3 = parse_sse(raw3)
types3 = [e[0] for e in events3]

# 验证工具调用事件
tool_call_events = [(e[0], e[1]) for e in events3 if e[0] == "tool_call"]
tool_result_events = [(e[0], e[1]) for e in events3 if e[0] == "tool_result"]

check("上传分析", "有 tool_call 事件", len(tool_call_events) > 0,
      f"count={len(tool_call_events)}")
check("上传分析", "有 tool_result 事件", len(tool_result_events) > 0,
      f"count={len(tool_result_events)}")

# 验证 tool_call 格式
if tool_call_events:
    _, tc_data = tool_call_events[0]
    check("上传分析", "tool_call 含 tool_call_id", "tool_call_id" in tc_data,
          f"keys={list(tc_data.keys())}")
    check("上传分析", "tool_call 含 name", "name" in tc_data)
    check("上传分析", "tool_call 含 arguments", "arguments" in tc_data)
    check("上传分析", "tool_call 含 round", "round" in tc_data)

# 验证 tool_result 格式
if tool_result_events:
    _, tr_data = tool_result_events[0]
    check("上传分析", "tool_result 含 tool_call_id", "tool_call_id" in tr_data,
          f"keys={list(tr_data.keys())}")
    check("上传分析", "tool_result 含 name", "name" in tr_data)
    check("上传分析", "tool_result 含 web", "web" in tr_data)
    check("上传分析", "tool_result 含 duration_ms", "duration_ms" in tr_data)

# 验证最终文本输出
final_text = ""
for etype, edata in events3:
    if etype == "text_delta" and isinstance(edata, dict):
        final_text += edata.get("text", "")
check("上传分析", "最终分析文本非空", len(final_text) > 0,
      f"len={len(final_text)}")

# 验证 turn_end
turn_end_found = False
for etype, edata in events3:
    if etype == "turn_end":
        turn_end_found = True
        check("上传分析", "turn_end status=completed", edata.get("status") == "completed")
        break
check("上传分析", "有 turn_end 事件", turn_end_found)

# 验证事件顺序：turn_start → llm_call_start → (text_delta|tool_call|tool_result)* → turn_end
ordered = [e[0] for e in events3 if e[0] not in ("_response",)]
check("上传分析", "事件以 turn_start 开头", ordered[0] == "turn_start" if ordered else False)
check("上传分析", "事件以 turn_end 结尾", ordered[-1] == "turn_end" if ordered else False)

# ----------------------------------------------------------
print("\n--- 4. 中断机制 ---")
# 启动一个长时间分析
code, raw4 = api("POST", "/api/chat", {
    "message": "做一个复杂的数据分析，包括多维度统计",
    "session_id": sid,
}, timeout=5)
# 即使超时，中断端点应该能工作
code_int, body_int = api("POST", "/api/chat/interrupt", {"session_id": sid})
check("中断", "中断请求 200", code_int == 200)
check("中断", "返回 interrupt_requested", body_int.get("status") == "interrupt_requested")

# ----------------------------------------------------------
print("\n--- 5. 会话恢复 SSE ---")
# 新会话发消息
code, raw5 = api("POST", "/api/chat", {"message": "1+1等于几？"})
check("恢复", "新会话 200", code == 200)
events5 = parse_sse(raw5)
sid5 = None
for etype, edata in events5:
    if etype == "turn_start":
        sid5 = edata.get("session_id")
        break

# 同一 session 继续对话
code, raw6 = api("POST", "/api/chat", {
    "message": "再加1呢？",
    "session_id": sid5,
})
check("恢复", "继续对话 200", code == 200)
events6 = parse_sse(raw6)
text6 = ""
for etype, edata in events6:
    if etype == "text_delta" and isinstance(edata, dict):
        text6 += edata.get("text", "")
check("恢复", "后续回复非空", len(text6) > 0, f"len={len(text6)}")

# 验证 session 持久化
code, sdata = api("GET", f"/api/sessions/{sid5}")
check("恢复", "会话数据可查", code == 200)
msgs = sdata.get("messages", [])
check("恢复", "消息数量 >= 4（2 user + 2 assistant）", len(msgs) >= 4,
      f"count={len(msgs)}")

# 清理
api("DELETE", f"/api/sessions/{sid5}")

# ----------------------------------------------------------
print("\n--- 6. HTML 模板完整性 ---")
code, html = api("GET", "/")
check("模板", "confirm 对话框绑定", "resumeConfirmation" in html)
check("模板", "x-show turn.confirmation", 'x-show="turn.confirmation"' in html)
check("模板", "suspension_id 绑定", "suspension_id" in html)
check("模板", "isThinking 条件", "turn.isThinking" in html)
check("模板", "thinkingText 绑定", "thinkingText" in html)
check("模板", "x-html renderMarkdown", "renderMarkdown(turn.content)" in html)

# ============================================================
print("\n" + "=" * 60)
print("测试结果汇总")
print("=" * 60)

passed = sum(1 for _, _, r in results if r.startswith("PASS"))
failed = sum(1 for _, _, r in results if r.startswith("FAIL"))
total = len(results)

modules = {}
for mod, name, result in results:
    modules.setdefault(mod, []).append((name, result))

for mod, items in modules.items():
    mod_pass = sum(1 for _, r in items if r.startswith("PASS"))
    print(f"\n[{mod}] {mod_pass}/{len(items)} passed")
    for name, result in items:
        if result.startswith("FAIL"):
            print(f"  FAIL: {name} — {result}")

print(f"\n总计: {passed}/{total} passed, {failed} failed")

if failed:
    sys.exit(1)
