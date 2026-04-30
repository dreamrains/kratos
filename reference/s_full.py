#!/usr/bin/env python3
# Harness: all mechanisms combined -- the complete cockpit for the model.
"""
s_full.py - Full Reference Agent

Capstone implementation combining every mechanism from s01-s11.
Session s12 (task-aware worktree isolation) is taught separately.
NOT a teaching session -- this is the "put it all together" reference.

    +------------------------------------------------------------------+
    |                        FULL AGENT                                 |
    |                                                                   |
    |  System prompt (s05 skills, task-first + optional todo nag)      |
    |                                                                   |
    |  Before each LLM call:                                            |
    |  +--------------------+  +------------------+  +--------------+  |
    |  | Microcompact (s06) |  | Drain bg (s08)   |  | Check inbox  |  |
    |  | Auto-compact (s06) |  | notifications    |  | (s09)        |  |
    |  +--------------------+  +------------------+  +--------------+  |
    |                                                                   |
    |  Tool dispatch (s02 pattern):                                     |
    |  +--------+----------+----------+---------+-----------+          |
    |  | bash   | read     | write    | edit    | TodoWrite |          |
    |  | task   | load_sk  | compress | bg_run  | bg_check  |          |
    |  | t_crt  | t_get    | t_upd    | t_list  | spawn_tm  |          |
    |  | list_tm| send_msg | rd_inbox | bcast   | shutdown  |          |
    |  | plan   | idle     | claim    |         |           |          |
    |  +--------+----------+----------+---------+-----------+          |
    |                                                                   |
    |  Subagent (s04):  spawn -> work -> return summary                 |
    |  Teammate (s09):  spawn -> work -> idle -> auto-claim (s11)      |
    |  Shutdown (s10):  request_id handshake                            |
    |  Plan gate (s10): submit -> approve/reject                        |
    +------------------------------------------------------------------+

    REPL commands: /compact /tasks /team /inbox
"""

import json
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)
if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

WORKDIR = Path.cwd()
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ["MODEL_ID"]

TEAM_DIR = WORKDIR / ".team"
INBOX_DIR = TEAM_DIR / "inbox"
TASKS_DIR = WORKDIR / ".tasks"
SKILLS_DIR = WORKDIR / "skills"
TRANSCRIPT_DIR = WORKDIR / ".transcripts"
SESSIONS_DIR = WORKDIR / "sessions"
TOKEN_THRESHOLD = 100000
POLL_INTERVAL = 5
IDLE_TIMEOUT = 60

VALID_MSG_TYPES = {"message", "broadcast", "shutdown_request",
                   "shutdown_response", "plan_approval_response"}


# === SECTION: tool_result ===
@dataclass
class ArtifactRef:
    """Reference to a file artifact produced by a tool."""
    path: str
    type: str  # "chart" | "report" | "report_md" | "file" | "analysis"
    description: str = ""


@dataclass
class ToolResult:
    """Structured return value for all tools.

    CLI uses ``summary`` for display; Web uses the full structure
    for rich rendering.  Existing tools that return plain strings
    are auto-wrapped via ``ToolResult.from_str()``.
    """
    summary: str
    data: dict[str, Any] | None = None
    artifacts: list[ArtifactRef] | None = None

    # -- convenience constructors --

    @staticmethod
    def from_str(s: str) -> "ToolResult":
        """Wrap a legacy plain-string return."""
        return ToolResult(summary=s)

    def to_cli(self) -> str:
        return self.summary

    def to_web(self) -> dict[str, Any]:
        result: dict[str, Any] = {"summary": self.summary}
        if self.data is not None:
            result["data"] = self.data
        if self.artifacts:
            result["artifacts"] = [
                {"path": a.path, "type": a.type, "description": a.description}
                for a in self.artifacts
            ]
        return result

    def __str__(self) -> str:
        return self.to_cli()


# === SECTION: loop_result ===

@dataclass
class FinalResponse:
    """Agent completed its answer; ready to display."""
    content: str


@dataclass
class SuspendedForConfirmation:
    """Agent paused at ask_user_question; awaiting user response."""
    suspension_id: str
    question: str
    options: list[dict[str, str]]
    context: str
    snapshot: dict  # serialized loop state


LoopResult = FinalResponse | SuspendedForConfirmation


class SuspensionManager:
    """Persist and restore agent loop suspensions.

    Suspensions are stored under ``sessions/{id}/suspension_{sid}.json``
    so they survive across CLI sessions and are accessible to Web API.
    """

    def __init__(self, sessions_dir: Path):
        self._dir = sessions_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, suspension: SuspendedForConfirmation) -> str:
        path = self._dir / f"suspension_{suspension.suspension_id}.json"
        path.write_text(json.dumps({
            "suspension_id": suspension.suspension_id,
            "question": suspension.question,
            "options": suspension.options,
            "context": suspension.context,
            "snapshot": suspension.snapshot,
        }, default=str, ensure_ascii=False))
        return str(path)

    def load(self, suspension_id: str) -> SuspendedForConfirmation | None:
        path = self._dir / f"suspension_{suspension_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return SuspendedForConfirmation(
            suspension_id=data["suspension_id"],
            question=data["question"],
            options=data["options"],
            context=data["context"],
            snapshot=data["snapshot"],
        )

    def remove(self, suspension_id: str):
        path = self._dir / f"suspension_{suspension_id}.json"
        path.unlink(missing_ok=True)


# === SECTION: base_tools ===
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"

def run_read(path: str, limit: int = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"

def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"

def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        c = fp.read_text()
        if old_text not in c:
            return f"Error: Text not found in {path}"
        fp.write_text(c.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


# === SECTION: todos (s03) ===
class TodoManager:
    def __init__(self):
        self.items = []

    def update(self, items: list) -> str:
        validated, ip = [], 0
        for i, item in enumerate(items):
            content = str(item.get("content", "")).strip()
            status = str(item.get("status", "pending")).lower()
            af = str(item.get("activeForm", "")).strip()
            if not content: raise ValueError(f"Item {i}: content required")
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Item {i}: invalid status '{status}'")
            if not af: raise ValueError(f"Item {i}: activeForm required")
            if status == "in_progress": ip += 1
            validated.append({"content": content, "status": status, "activeForm": af})
        if len(validated) > 20: raise ValueError("Max 20 todos")
        if ip > 1: raise ValueError("Only one in_progress allowed")
        self.items = validated
        return self.render()

    def render(self) -> str:
        if not self.items: return "No todos."
        lines = []
        for item in self.items:
            m = {"completed": "[x]", "in_progress": "[>]", "pending": "[ ]"}.get(item["status"], "[?]")
            suffix = f" <- {item['activeForm']}" if item["status"] == "in_progress" else ""
            lines.append(f"{m} {item['content']}{suffix}")
        done = sum(1 for t in self.items if t["status"] == "completed")
        lines.append(f"\n({done}/{len(self.items)} completed)")
        return "\n".join(lines)

    def has_open_items(self) -> bool:
        return any(item.get("status") != "completed" for item in self.items)


# === SECTION: subagent (s04) ===
def run_subagent(prompt: str, agent_type: str = "Explore") -> str:
    sub_tools = [
        {"name": "bash", "description": "Run command.",
         "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
        {"name": "read_file", "description": "Read file.",
         "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    ]
    if agent_type != "Explore":
        sub_tools += [
            {"name": "write_file", "description": "Write file.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
            {"name": "edit_file", "description": "Edit file.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
        ]
    sub_handlers = {
        "bash": lambda **kw: run_bash(kw["command"]),
        "read_file": lambda **kw: run_read(kw["path"]),
        "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
        "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    }
    sub_msgs = [{"role": "user", "content": prompt}]
    resp = None
    for _ in range(30):
        resp = client.messages.create(model=MODEL, messages=sub_msgs, tools=sub_tools, max_tokens=8000)
        sub_msgs.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            break
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                h = sub_handlers.get(b.name, lambda **kw: "Unknown tool")
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(h(**b.input))[:50000]})
        sub_msgs.append({"role": "user", "content": results})
    if resp:
        return "".join(b.text for b in resp.content if hasattr(b, "text")) or "(no summary)"
    return "(subagent failed)"


# === SECTION: skills (s05) ===
class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills = {}
        if skills_dir.exists():
            for f in sorted(skills_dir.rglob("SKILL.md")):
                text = f.read_text()
                match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
                meta, body = {}, text
                if match:
                    for line in match.group(1).strip().splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            meta[k.strip()] = v.strip()
                    body = match.group(2).strip()
                name = meta.get("name", f.parent.name)
                self.skills[name] = {"meta": meta, "body": body}

    def descriptions(self) -> str:
        if not self.skills: return "(no skills)"
        return "\n".join(f"  - {n}: {s['meta'].get('description', '-')}" for n, s in self.skills.items())

    def load(self, name: str) -> str:
        s = self.skills.get(name)
        if not s: return f"Error: Unknown skill '{name}'. Available: {', '.join(self.skills.keys())}"
        return f"<skill name=\"{name}\">\n{s['body']}\n</skill>"


# === SECTION: compression (s06) ===
def estimate_tokens(messages: list) -> int:
    return len(json.dumps(messages, default=str)) // 4

def microcompact(messages: list):
    indices = []
    for i, msg in enumerate(messages):
        if msg["role"] == "user" and isinstance(msg.get("content"), list):
            for part in msg["content"]:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    indices.append(part)
    if len(indices) <= 3:
        return
    for part in indices[:-3]:
        if isinstance(part.get("content"), str) and len(part["content"]) > 100:
            part["content"] = "[cleared]"

def auto_compact(messages: list) -> list:
    TRANSCRIPT_DIR.mkdir(exist_ok=True)
    path = TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"
    with open(path, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str) + "\n")
    conv_text = json.dumps(messages, default=str)[-80000:]
    resp = client.messages.create(
        model=MODEL,
        messages=[{"role": "user", "content": f"Summarize for continuity:\n{conv_text}"}],
        max_tokens=2000,
    )
    summary = resp.content[0].text
    return [
        {"role": "user", "content": f"[Compressed. Transcript: {path}]\n{summary}"},
    ]


# === SECTION: file_tasks (s07) ===
class TaskManager:
    def __init__(self):
        TASKS_DIR.mkdir(exist_ok=True)

    def _next_id(self) -> int:
        ids = [int(f.stem.split("_")[1]) for f in TASKS_DIR.glob("task_*.json")]
        return max(ids, default=0) + 1

    def _load(self, tid: int) -> dict:
        p = TASKS_DIR / f"task_{tid}.json"
        if not p.exists(): raise ValueError(f"Task {tid} not found")
        return json.loads(p.read_text())

    def _save(self, task: dict):
        (TASKS_DIR / f"task_{task['id']}.json").write_text(json.dumps(task, indent=2))

    def create(self, subject: str, description: str = "") -> str:
        task = {"id": self._next_id(), "subject": subject, "description": description,
                "status": "pending", "owner": None, "blockedBy": []}
        self._save(task)
        return json.dumps(task, indent=2)

    def get(self, tid: int) -> str:
        return json.dumps(self._load(tid), indent=2)

    def update(self, tid: int, status: str = None,
               add_blocked_by: list = None, remove_blocked_by: list = None) -> str:
        task = self._load(tid)
        if status:
            task["status"] = status
            if status == "completed":
                for f in TASKS_DIR.glob("task_*.json"):
                    t = json.loads(f.read_text())
                    if tid in t.get("blockedBy", []):
                        t["blockedBy"].remove(tid)
                        self._save(t)
            if status == "deleted":
                (TASKS_DIR / f"task_{tid}.json").unlink(missing_ok=True)
                return f"Task {tid} deleted"
        if add_blocked_by:
            task["blockedBy"] = list(set(task["blockedBy"] + add_blocked_by))
        if remove_blocked_by:
            task["blockedBy"] = [x for x in task["blockedBy"] if x not in remove_blocked_by]
        self._save(task)
        return json.dumps(task, indent=2)

    def list_all(self) -> str:
        tasks = [json.loads(f.read_text()) for f in sorted(TASKS_DIR.glob("task_*.json"))]
        if not tasks: return "No tasks."
        lines = []
        for t in tasks:
            m = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}.get(t["status"], "[?]")
            owner = f" @{t['owner']}" if t.get("owner") else ""
            blocked = f" (blocked by: {t['blockedBy']})" if t.get("blockedBy") else ""
            lines.append(f"{m} #{t['id']}: {t['subject']}{owner}{blocked}")
        return "\n".join(lines)

    def claim(self, tid: int, owner: str) -> str:
        task = self._load(tid)
        task["owner"] = owner
        task["status"] = "in_progress"
        self._save(task)
        return f"Claimed task #{tid} for {owner}"


# === SECTION: background (s08) ===
class BackgroundManager:
    def __init__(self):
        self.tasks = {}
        self.notifications = Queue()

    def run(self, command: str, timeout: int = 120) -> str:
        tid = str(uuid.uuid4())[:8]
        self.tasks[tid] = {"status": "running", "command": command, "result": None}
        threading.Thread(target=self._exec, args=(tid, command, timeout), daemon=True).start()
        return f"Background task {tid} started: {command[:80]}"

    def _exec(self, tid: str, command: str, timeout: int):
        try:
            r = subprocess.run(command, shell=True, cwd=WORKDIR,
                               capture_output=True, text=True, timeout=timeout)
            output = (r.stdout + r.stderr).strip()[:50000]
            self.tasks[tid].update({"status": "completed", "result": output or "(no output)"})
        except Exception as e:
            self.tasks[tid].update({"status": "error", "result": str(e)})
        self.notifications.put({"task_id": tid, "status": self.tasks[tid]["status"],
                                "result": self.tasks[tid]["result"][:500]})

    def check(self, tid: str = None) -> str:
        if tid:
            t = self.tasks.get(tid)
            return f"[{t['status']}] {t.get('result') or '(running)'}" if t else f"Unknown: {tid}"
        return "\n".join(f"{k}: [{v['status']}] {v['command'][:60]}" for k, v in self.tasks.items()) or "No bg tasks."

    def drain(self) -> list:
        notifs = []
        while not self.notifications.empty():
            notifs.append(self.notifications.get_nowait())
        return notifs


# === SECTION: messaging (s09) ===
class MessageBus:
    def __init__(self):
        INBOX_DIR.mkdir(parents=True, exist_ok=True)

    def send(self, sender: str, to: str, content: str,
             msg_type: str = "message", extra: dict = None) -> str:
        msg = {"type": msg_type, "from": sender, "content": content,
               "timestamp": time.time()}
        if extra: msg.update(extra)
        with open(INBOX_DIR / f"{to}.jsonl", "a") as f:
            f.write(json.dumps(msg) + "\n")
        return f"Sent {msg_type} to {to}"

    def read_inbox(self, name: str) -> list:
        path = INBOX_DIR / f"{name}.jsonl"
        if not path.exists(): return []
        msgs = [json.loads(l) for l in path.read_text().strip().splitlines() if l]
        path.write_text("")
        return msgs

    def broadcast(self, sender: str, content: str, names: list) -> str:
        count = 0
        for n in names:
            if n != sender:
                self.send(sender, n, content, "broadcast")
                count += 1
        return f"Broadcast to {count} teammates"


# === SECTION: shutdown + plan tracking (s10) ===
shutdown_requests = {}
plan_requests = {}


# === SECTION: team (s09/s11) ===
class TeammateManager:
    def __init__(self, bus: MessageBus, task_mgr: TaskManager):
        TEAM_DIR.mkdir(exist_ok=True)
        self.bus = bus
        self.task_mgr = task_mgr
        self.config_path = TEAM_DIR / "config.json"
        self.config = self._load()
        self.threads = {}

    def _load(self) -> dict:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text())
        return {"team_name": "default", "members": []}

    def _save(self):
        self.config_path.write_text(json.dumps(self.config, indent=2))

    def _find(self, name: str) -> dict:
        for m in self.config["members"]:
            if m["name"] == name: return m
        return None

    def spawn(self, name: str, role: str, prompt: str) -> str:
        member = self._find(name)
        if member:
            if member["status"] not in ("idle", "shutdown"):
                return f"Error: '{name}' is currently {member['status']}"
            member["status"] = "working"
            member["role"] = role
        else:
            member = {"name": name, "role": role, "status": "working"}
            self.config["members"].append(member)
        self._save()
        threading.Thread(target=self._loop, args=(name, role, prompt), daemon=True).start()
        return f"Spawned '{name}' (role: {role})"

    def _set_status(self, name: str, status: str):
        member = self._find(name)
        if member:
            member["status"] = status
            self._save()

    def _loop(self, name: str, role: str, prompt: str):
        team_name = self.config["team_name"]
        sys_prompt = (f"You are '{name}', role: {role}, team: {team_name}, at {WORKDIR}. "
                      f"Use idle when done with current work. You may auto-claim tasks.")
        messages = [{"role": "user", "content": prompt}]
        tools = [
            {"name": "bash", "description": "Run command.", "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
            {"name": "read_file", "description": "Read file.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
            {"name": "write_file", "description": "Write file.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
            {"name": "edit_file", "description": "Edit file.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
            {"name": "send_message", "description": "Send message.", "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}}, "required": ["to", "content"]}},
            {"name": "idle", "description": "Signal no more work.", "input_schema": {"type": "object", "properties": {}}},
            {"name": "claim_task", "description": "Claim task by ID.", "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
        ]
        while True:
            # -- WORK PHASE --
            for _ in range(50):
                inbox = self.bus.read_inbox(name)
                for msg in inbox:
                    if msg.get("type") == "shutdown_request":
                        self._set_status(name, "shutdown")
                        return
                    messages.append({"role": "user", "content": json.dumps(msg)})
                try:
                    response = client.messages.create(
                        model=MODEL, system=sys_prompt, messages=messages,
                        tools=tools, max_tokens=8000)
                except Exception:
                    self._set_status(name, "shutdown")
                    return
                messages.append({"role": "assistant", "content": response.content})
                if response.stop_reason != "tool_use":
                    break
                results = []
                idle_requested = False
                for block in response.content:
                    if block.type == "tool_use":
                        if block.name == "idle":
                            idle_requested = True
                            output = "Entering idle phase."
                        elif block.name == "claim_task":
                            output = self.task_mgr.claim(block.input["task_id"], name)
                        elif block.name == "send_message":
                            output = self.bus.send(name, block.input["to"], block.input["content"])
                        else:
                            dispatch = {"bash": lambda **kw: run_bash(kw["command"]),
                                        "read_file": lambda **kw: run_read(kw["path"]),
                                        "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
                                        "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"])}
                            output = dispatch.get(block.name, lambda **kw: "Unknown")(**block.input)
                        print(f"  [{name}] {block.name}: {str(output)[:120]}")
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
                messages.append({"role": "user", "content": results})
                if idle_requested:
                    break
            # -- IDLE PHASE: poll for messages and unclaimed tasks --
            self._set_status(name, "idle")
            resume = False
            for _ in range(IDLE_TIMEOUT // max(POLL_INTERVAL, 1)):
                time.sleep(POLL_INTERVAL)
                inbox = self.bus.read_inbox(name)
                if inbox:
                    for msg in inbox:
                        if msg.get("type") == "shutdown_request":
                            self._set_status(name, "shutdown")
                            return
                        messages.append({"role": "user", "content": json.dumps(msg)})
                    resume = True
                    break
                unclaimed = []
                for f in sorted(TASKS_DIR.glob("task_*.json")):
                    t = json.loads(f.read_text())
                    if t.get("status") == "pending" and not t.get("owner") and not t.get("blockedBy"):
                        unclaimed.append(t)
                if unclaimed:
                    task = unclaimed[0]
                    self.task_mgr.claim(task["id"], name)
                    # Identity re-injection for compressed contexts
                    if len(messages) <= 3:
                        messages.insert(0, {"role": "user", "content":
                            f"<identity>You are '{name}', role: {role}, team: {team_name}.</identity>"})
                        messages.insert(1, {"role": "assistant", "content": f"I am {name}. Continuing."})
                    messages.append({"role": "user", "content":
                        f"<auto-claimed>Task #{task['id']}: {task['subject']}\n{task.get('description', '')}</auto-claimed>"})
                    messages.append({"role": "assistant", "content": f"Claimed task #{task['id']}. Working on it."})
                    resume = True
                    break
            if not resume:
                self._set_status(name, "shutdown")
                return
            self._set_status(name, "working")

    def list_all(self) -> str:
        if not self.config["members"]: return "No teammates."
        lines = [f"Team: {self.config['team_name']}"]
        for m in self.config["members"]:
            lines.append(f"  {m['name']} ({m['role']}): {m['status']}")
        return "\n".join(lines)

    def member_names(self) -> list:
        return [m["name"] for m in self.config["members"]]


# === SECTION: global_instances ===
TODO = TodoManager()
SKILLS = SkillLoader(SKILLS_DIR)
TASK_MGR = TaskManager()
BG = BackgroundManager()
BUS = MessageBus()
TEAM = TeammateManager(BUS, TASK_MGR)
SUSPENSIONS = SuspensionManager(SESSIONS_DIR)

# === SECTION: system_prompt ===
SYSTEM = f"""You are a coding agent at {WORKDIR}. Use tools to solve tasks.
Prefer task_create/task_update/task_list for multi-step work. Use TodoWrite for short checklists.
Use task for subagent delegation. Use load_skill for specialized knowledge.
Skills: {SKILLS.descriptions()}"""


# === SECTION: shutdown_protocol (s10) ===
def handle_shutdown_request(teammate: str) -> str:
    req_id = str(uuid.uuid4())[:8]
    shutdown_requests[req_id] = {"target": teammate, "status": "pending"}
    BUS.send("lead", teammate, "Please shut down.", "shutdown_request", {"request_id": req_id})
    return f"Shutdown request {req_id} sent to '{teammate}'"

# === SECTION: plan_approval (s10) ===
def handle_plan_review(request_id: str, approve: bool, feedback: str = "") -> str:
    req = plan_requests.get(request_id)
    if not req: return f"Error: Unknown plan request_id '{request_id}'"
    req["status"] = "approved" if approve else "rejected"
    BUS.send("lead", req["from"], feedback, "plan_approval_response",
             {"request_id": request_id, "approve": approve, "feedback": feedback})
    return f"Plan {req['status']} for '{req['from']}'"


# === SECTION: assess_readiness (L1) ===
import math
from datetime import datetime, timedelta


def assess_readiness_tool(
    dataset_info: dict,
    quality_info: dict | None = None,
    intent: str = "",
    loaded_tables: int = 1,
) -> ToolResult:
    """Evaluate data readiness for the planned analysis.

    Returns a structured readiness report with severity-tagged findings.
    Does NOT block analysis — the LLM decides whether to surface warnings
    to the user via ask_user_question.
    """
    findings = []
    row_count = dataset_info.get("row_count", 0)
    columns = dataset_info.get("columns", [])
    datetime_cols = dataset_info.get("datetime_columns", [])
    missing_rates = dataset_info.get("missing_rates", {})
    quality = quality_info or {}

    # --- 1. Time granularity consistency ---
    for dt_col in datetime_cols:
        col_name = dt_col.get("name", "")
        intervals = dt_col.get("intervals", [])
        if not intervals or len(intervals) < 2:
            continue
        # Check if intervals are roughly uniform (within 20% tolerance)
        avg_interval = sum(intervals) / len(intervals)
        non_uniform = [iv for iv in intervals if abs(iv - avg_interval) / max(avg_interval, 1) > 0.2]
        if non_uniform and len(non_uniform) / len(intervals) > 0.1:
            findings.append({
                "severity": "warning",
                "check": "time_granularity",
                "message": f"时间列 '{col_name}' 间隔不一致：约{len(non_uniform)}/{len(intervals)}个间隔偏离均值{avg_interval:.1f}天超过20%，建议统一后再做趋势分析",
            })

    # --- 2. Sample size sufficiency (intent-specific) ---
    ml_intents = {"forecast", "classification"}
    if intent in ml_intents:
        min_rows = 200 if intent == "classification" else 100
        if row_count < min_rows:
            findings.append({
                "severity": "warning",
                "check": "sample_size",
                "message": f"当前{row_count}行数据，{intent}建模建议≥{min_rows}行，结果置信度可能较低",
            })

    # --- 3. Key column missing rate ---
    high_missing = quality.get("high_missing_columns", {})
    if not high_missing and missing_rates:
        high_missing = {k: v for k, v in missing_rates.items() if v > 0.3}
    for col_name, rate in high_missing.items():
        severity = "block" if rate > 0.5 else "warning"
        findings.append({
            "severity": severity,
            "check": "missing_data",
            "message": f"列 '{col_name}' 缺失率 {rate:.0%}，{'分析结果可能不可靠' if severity == 'block' else '部分分析可能受影响'}",
        })

    # --- 4. Constant / near-constant columns ---
    constant_cols = quality.get("constant_columns", [])
    for col_name in constant_cols:
        findings.append({
            "severity": "info",
            "check": "constant_column",
            "message": f"列 '{col_name}' 仅含单一值或方差≈0，无法用于维度拆解或相关性分析",
        })

    # --- 5. Multi-table relationship ---
    if loaded_tables > 1:
        findings.append({
            "severity": "warning",
            "check": "multi_table",
            "message": f"检测到{loaded_tables}个DataFrame已加载，未指定关联键。多表分析前建议确认主键/外键关系",
        })

    # --- 6. Data freshness ---
    for dt_col in datetime_cols:
        max_date_str = dt_col.get("max_date", "")
        if max_date_str:
            try:
                max_date = datetime.fromisoformat(str(max_date_str)[:10])
                days_old = (datetime.now() - max_date).days
                if days_old > 7:
                    findings.append({
                        "severity": "info",
                        "check": "data_freshness",
                        "message": f"数据最新日期 {max_date_str[:10]}，距今{days_old}天",
                    })
            except (ValueError, TypeError):
                pass

    # --- Compute overall readiness ---
    has_block = any(f["severity"] == "block" for f in findings)
    has_warning = any(f["severity"] == "warning" for f in findings)
    if has_block:
        overall = "blocked"
    elif has_warning:
        overall = "ready_with_warnings"
    else:
        overall = "ready"

    # Build summary for CLI
    icon_map = {"block": "🔴", "warning": "⚠️", "info": "ℹ️"}
    summary_lines = [f"Data Readiness: {overall}"]
    for f in findings:
        summary_lines.append(f"  {icon_map.get(f['severity'], '?')} {f['message']}")
    if not findings:
        summary_lines.append("  ✅ 所有检查通过，数据已就绪")

    return ToolResult(
        summary="\n".join(summary_lines),
        data={
            "overall": overall,
            "findings": findings,
            "checks_run": 6,
        },
    )


# === SECTION: tool_dispatch (s02) ===

def _tr(result) -> ToolResult:
    """Normalize any tool return to ToolResult."""
    if isinstance(result, ToolResult):
        return result
    return ToolResult.from_str(str(result))


TOOL_HANDLERS = {
    "bash":             lambda **kw: run_bash(kw["command"]),
    "read_file":        lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file":       lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":        lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "TodoWrite":        lambda **kw: TODO.update(kw["items"]),
    "task":             lambda **kw: run_subagent(kw["prompt"], kw.get("agent_type", "Explore")),
    "load_skill":       lambda **kw: SKILLS.load(kw["name"]),
    "compress":         lambda **kw: "Compressing...",
    "background_run":   lambda **kw: BG.run(kw["command"], kw.get("timeout", 120)),
    "check_background": lambda **kw: BG.check(kw.get("task_id")),
    "task_create":      lambda **kw: TASK_MGR.create(kw["subject"], kw.get("description", "")),
    "task_get":         lambda **kw: TASK_MGR.get(kw["task_id"]),
    "task_update":      lambda **kw: TASK_MGR.update(kw["task_id"], kw.get("status"), kw.get("add_blocked_by"), kw.get("remove_blocked_by")),
    "task_list":        lambda **kw: TASK_MGR.list_all(),
    "spawn_teammate":   lambda **kw: TEAM.spawn(kw["name"], kw["role"], kw["prompt"]),
    "list_teammates":   lambda **kw: TEAM.list_all(),
    "send_message":     lambda **kw: BUS.send("lead", kw["to"], kw["content"], kw.get("msg_type", "message")),
    "read_inbox":       lambda **kw: json.dumps(BUS.read_inbox("lead"), indent=2),
    "broadcast":        lambda **kw: BUS.broadcast("lead", kw["content"], TEAM.member_names()),
    "shutdown_request": lambda **kw: handle_shutdown_request(kw["teammate"]),
    "plan_approval":    lambda **kw: handle_plan_review(kw["request_id"], kw["approve"], kw.get("feedback", "")),
    "idle":             lambda **kw: "Lead does not idle.",
    "claim_task":       lambda **kw: TASK_MGR.claim(kw["task_id"], "lead"),
    "assess_readiness": lambda **kw: assess_readiness_tool(
                            dataset_info=kw.get("dataset_info", {}),
                            quality_info=kw.get("quality_info"),
                            intent=kw.get("intent", ""),
                            loaded_tables=kw.get("loaded_tables", 1),
                        ),
}

TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "TodoWrite", "description": "Update task tracking list.",
     "input_schema": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"content": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}, "activeForm": {"type": "string"}}, "required": ["content", "status", "activeForm"]}}}, "required": ["items"]}},
    {"name": "task", "description": "Spawn a subagent for isolated exploration or work.",
     "input_schema": {"type": "object", "properties": {"prompt": {"type": "string"}, "agent_type": {"type": "string", "enum": ["Explore", "general-purpose"]}}, "required": ["prompt"]}},
    {"name": "load_skill", "description": "Load specialized knowledge by name.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "compress", "description": "Manually compress conversation context.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "background_run", "description": "Run command in background thread.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["command"]}},
    {"name": "check_background", "description": "Check background task status.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}}},
    {"name": "task_create", "description": "Create a persistent file task.",
     "input_schema": {"type": "object", "properties": {"subject": {"type": "string"}, "description": {"type": "string"}}, "required": ["subject"]}},
    {"name": "task_get", "description": "Get task details by ID.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
    {"name": "task_update", "description": "Update task status or dependencies.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]}, "add_blocked_by": {"type": "array", "items": {"type": "integer"}}, "remove_blocked_by": {"type": "array", "items": {"type": "integer"}}}, "required": ["task_id"]}},
    {"name": "task_list", "description": "List all tasks.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "spawn_teammate", "description": "Spawn a persistent autonomous teammate.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "role": {"type": "string"}, "prompt": {"type": "string"}}, "required": ["name", "role", "prompt"]}},
    {"name": "list_teammates", "description": "List all teammates.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "send_message", "description": "Send a message to a teammate.",
     "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}, "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)}}, "required": ["to", "content"]}},
    {"name": "read_inbox", "description": "Read and drain the lead's inbox.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "broadcast", "description": "Send message to all teammates.",
     "input_schema": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}},
    {"name": "shutdown_request", "description": "Request a teammate to shut down.",
     "input_schema": {"type": "object", "properties": {"teammate": {"type": "string"}}, "required": ["teammate"]}},
    {"name": "plan_approval", "description": "Approve or reject a teammate's plan.",
     "input_schema": {"type": "object", "properties": {"request_id": {"type": "string"}, "approve": {"type": "boolean"}, "feedback": {"type": "string"}}, "required": ["request_id", "approve"]}},
    {"name": "idle", "description": "Enter idle state.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "claim_task", "description": "Claim a task from the board.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
    {"name": "ask_user_question", "description": "Ask user a question and wait for their response. Use when intent is ambiguous, metric definition is missing, or before risky operations.",
     "input_schema": {"type": "object", "properties": {
         "question": {"type": "string", "description": "Clear question to ask the user"},
         "options": {"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}, "description": {"type": "string"}}, "required": ["label"]}, "description": "Pre-defined options for the user to choose from"},
         "context": {"type": "string", "description": "Background context for why this question is being asked"}
     }, "required": ["question"]}},
    {"name": "assess_readiness", "description": "Assess data readiness for analysis. Checks time granularity consistency, sample size sufficiency, key column completeness, constant columns, multi-table relationships, and data freshness. Returns a readiness report with severity levels (info/warning/block).",
     "input_schema": {"type": "object", "properties": {
         "dataset_info": {"type": "object", "description": "Output from describe_dataset: field types, row count, datetime ranges, etc.", "properties": {
             "row_count": {"type": "integer"},
             "columns": {"type": "array", "items": {"type": "object"}},
             "datetime_columns": {"type": "array", "items": {"type": "object"}},
             "missing_rates": {"type": "object"}
         }},
         "quality_info": {"type": "object", "description": "Output from detect_data_quality: outliers, duplicates, constant columns.", "properties": {
             "constant_columns": {"type": "array", "items": {"type": "string"}},
             "high_missing_columns": {"type": "object"},
             "duplicate_rate": {"type": "number"}
         }},
         "intent": {"type": "string", "description": "Optional analysis intent (forecast, attribution, exploration, etc.) to enable intent-specific checks.", "enum": ["forecast", "classification", "attribution", "comparison", "anomaly", "exploration", "full_report", ""]},
         "loaded_tables": {"type": "integer", "description": "Number of currently loaded DataFrames.", "default": 1}
     }, "required": ["dataset_info"]}},
]


# === SECTION: agent_loop ===
def agent_loop(messages: list) -> LoopResult:
    """Run one or more agent iterations.

    Returns:
        FinalResponse  – agent finished answering
        SuspendedForConfirmation – agent needs user input to continue

    Call ``resume_loop()`` with the user's response to continue from a
    ``SuspendedForConfirmation``.
    """
    rounds_without_todo = 0
    while True:
        # s06: compression pipeline
        microcompact(messages)
        if estimate_tokens(messages) > TOKEN_THRESHOLD:
            print("[auto-compact triggered]")
            messages[:] = auto_compact(messages)
        # s08: drain background notifications
        notifs = BG.drain()
        if notifs:
            txt = "\n".join(f"[bg:{n['task_id']}] {n['status']}: {n['result']}" for n in notifs)
            messages.append({"role": "user", "content": f"<background-results>\n{txt}\n</background-results>"})
        # s10: check lead inbox
        inbox = BUS.read_inbox("lead")
        if inbox:
            messages.append({"role": "user", "content": f"<inbox>{json.dumps(inbox, indent=2)}</inbox>"})
        # LLM call
        response = client.messages.create(
            model=MODEL, system=SYSTEM, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            # Extract final text response
            text_parts = [b.text for b in response.content if hasattr(b, "text")]
            return FinalResponse(content="\n".join(text_parts))
        # Tool execution
        results = []
        used_todo = False
        manual_compress = False
        suspended = False
        for block in response.content:
            if block.type == "tool_use":
                if block.name == "compress":
                    manual_compress = True
                # Handle ask_user_question: suspend loop
                if block.name == "ask_user_question":
                    suspended = True
                    sid = str(uuid.uuid4())[:8]
                    inp = block.input
                    susp = SuspendedForConfirmation(
                        suspension_id=sid,
                        question=inp.get("question", ""),
                        options=inp.get("options", []),
                        context=inp.get("context", ""),
                        snapshot={"messages": _serialize_messages(messages)},
                    )
                    SUSPENSIONS.save(susp)
                    # Tell LLM we're waiting for user input
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Suspended for user confirmation. suspension_id={sid}",
                    })
                    continue
                handler = TOOL_HANDLERS.get(block.name)
                try:
                    raw_output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
                except Exception as e:
                    raw_output = f"Error: {e}"
                tool_result = _tr(raw_output)
                print(f"> {block.name}:")
                print(tool_result.to_cli()[:200])
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": tool_result.to_cli()})
                if block.name == "TodoWrite":
                    used_todo = True
        # s03: nag reminder
        rounds_without_todo = 0 if used_todo else rounds_without_todo + 1
        if TODO.has_open_items() and rounds_without_todo >= 3:
            results.append({"type": "text", "text": "<reminder>Update your todos.</reminder>"})
        messages.append({"role": "user", "content": results})
        # s06: manual compress
        if manual_compress:
            print("[manual compact]")
            messages[:] = auto_compact(messages)
            return FinalResponse(content="[context compressed]")
        # If suspended, return suspension to caller
        if suspended:
            return susp


def resume_loop(suspension_id: str, user_response: str) -> LoopResult:
    """Resume agent loop after user answers a suspended question."""
    susp = SUSPENSIONS.load(suspension_id)
    if not susp:
        return FinalResponse(content=f"Error: suspension {suspension_id} not found")
    messages = _deserialize_messages(susp.snapshot["messages"])
    # Append the suspension context and user's response
    messages.append({"role": "user", "content": (
        f"<confirmation_response suspension_id=\"{suspension_id}\">\n"
        f"Question: {susp.question}\n"
        f"User answered: {user_response}\n"
        f"</confirmation_response>"
    )})
    SUSPENSIONS.remove(suspension_id)
    return agent_loop(messages)


def _serialize_messages(messages: list) -> list:
    """Serialize message list for suspension storage."""
    serialized = []
    for msg in messages:
        m = {"role": msg["role"]}
        content = msg.get("content")
        if isinstance(content, str):
            m["content"] = content
        elif isinstance(content, list):
            # Handle list of content blocks (tool results, etc.)
            parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "tool_result":
                        parts.append({"type": "tool_result", "tool_use_id": part.get("tool_use_id", ""),
                                      "content": str(part.get("content", ""))[:5000]})
                    elif part.get("type") == "text":
                        parts.append({"type": "text", "text": part.get("text", "")})
                    else:
                        parts.append(str(part)[:500])
                else:
                    parts.append(str(part)[:500])
            m["content"] = parts
        else:
            m["content"] = str(content)[:5000]
        serialized.append(m)
    return serialized


def _deserialize_messages(data: list) -> list:
    """Deserialize messages back from suspension storage."""
    return data


# === SECTION: command_registry ===
class CommandRegistry:
    """Pluggable command registry.

    CLI triggers via ``/command [args]``; Web triggers via
    ``POST /api/command/<name>``.  Both share the same handler.
    """

    def __init__(self):
        self._commands: dict[str, dict[str, Any]] = {}

    def register(self, name: str, handler: callable, description: str = "",
                 aliases: list[str] | None = None):
        entry = {"handler": handler, "description": description, "aliases": aliases or []}
        self._commands[name] = entry
        for alias in (aliases or []):
            self._commands[alias] = {**entry, "alias_of": name}

    def execute(self, name: str, args: str = "") -> ToolResult:
        entry = self._commands.get(name)
        if not entry:
            return ToolResult(summary=f"Unknown command: /{name}. Type /help for available commands.")
        return _tr(entry["handler"](args))

    def list_commands(self) -> str:
        seen = set()
        lines = ["Available commands:"]
        for name, entry in self._commands.items():
            if "alias_of" in entry:
                continue
            seen.add(name)
            desc = entry.get("description", "")
            aliases = entry.get("aliases", [])
            alias_str = f" ({', '.join('/' + a for a in aliases)})" if aliases else ""
            lines.append(f"  /{name}{alias_str}  - {desc}")
        return "\n".join(lines)


def _build_command_registry() -> CommandRegistry:
    reg = CommandRegistry()

    def cmd_help(args: str) -> str:
        return reg.list_commands()

    def cmd_compact(args: str) -> str:
        if not history_ref[0]:
            return "No conversation to compact."
        print("[manual compact via /compact]")
        history_ref[0][:] = auto_compact(history_ref[0])
        return "Context compressed."

    def cmd_tasks(args: str) -> str:
        return TASK_MGR.list_all()

    def cmd_team(args: str) -> str:
        return TEAM.list_all()

    def cmd_inbox(args: str) -> str:
        return json.dumps(BUS.read_inbox("lead"), indent=2)

    reg.register("help", cmd_help, "Show available commands", aliases=["h", "?"])
    reg.register("compact", cmd_compact, "Manually compress conversation context")
    reg.register("tasks", cmd_tasks, "List all file tasks")
    reg.register("team", cmd_team, "List teammates")
    reg.register("inbox", cmd_inbox, "Read and drain lead inbox")
    return reg


# === SECTION: repl ===
def _display_options(options: list[dict]) -> str:
    """Format options for CLI display."""
    lines = []
    for i, opt in enumerate(options, 1):
        label = opt.get("label", "")
        desc = opt.get("description", "")
        lines.append(f"  {i}. {label}" + (f" - {desc}" if desc else ""))
    lines.append(f"  {len(options) + 1}. (free input)")
    return "\n".join(lines)


def _handle_cli_loop_result(result: LoopResult, history: list):
    """Handle LoopResult in CLI: display response or prompt for confirmation."""
    if isinstance(result, FinalResponse):
        print(result.content)
        return
    # SuspendedForConfirmation
    print(f"\n\033[33m[Confirmation required]\033[0m {result.question}")
    if result.options:
        print(_display_options(result.options))
    while True:
        try:
            answer = input("\033[33mYour answer: \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if not answer:
            continue
        # Map numeric selection to option label
        if result.options and answer.isdigit():
            idx = int(answer) - 1
            if 0 <= idx < len(result.options):
                answer = result.options[idx]["label"]
            elif idx == len(result.options):
                pass  # free input, keep as-is
            else:
                print("Invalid selection. Try again.")
                continue
        break
    # Resume loop with user's answer
    resume_result = resume_loop(result.suspension_id, answer)
    _handle_cli_loop_result(resume_result, history)


if __name__ == "__main__":
    history = []
    history_ref = [history]  # mutable reference for command handlers
    CMD = _build_command_registry()

    while True:
        try:
            query = input("\033[36ms_full >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        stripped = query.strip()
        if stripped.lower() in ("q", "exit", ""):
            break
        # Command dispatch via registry
        if stripped.startswith("/"):
            parts = stripped[1:].split(None, 1)
            cmd_name = parts[0] if parts else ""
            cmd_args = parts[1] if len(parts) > 1 else ""
            result = CMD.execute(cmd_name, cmd_args)
            print(result.to_cli())
            continue
        history.append({"role": "user", "content": query})
        result = agent_loop(history)
        _handle_cli_loop_result(result, history)
        print()
