"""用户交互工具：ask_user_question。参考 Claude Code 的 AskUserQuestion 设计。

支持模式：
- 单问题模式：question + options
- 多问题模式：questions JSON 数组（1-4 个问题，顺序提问）
"""

from __future__ import annotations

import json
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from data_agent.tools.registry import registry

console = Console()

# ── 交互式工具禁用超时（等待用户输入可能很长）───────────────
registry.set_timeout("ask_user_question", 0)


# ── 输入函数 ──────────────────────────────────────────────

def _robust_input(prompt_text: str = "", default: str = "") -> str:
    """获取用户输入，确保文字可见。prompt_toolkit 优先，fallback 到 input()。

    Args:
        prompt_text: 提示符文本
        default: 空输入时的默认返回值

    Returns:
        用户输入的文本（已 strip），空输入返回 default。
    """
    # 尝试 prompt_toolkit（文字着色、更好的终端兼容性）
    try:
        from prompt_toolkit import prompt as pt_prompt
        from prompt_toolkit.formatted_text import FormattedText
        from prompt_toolkit.styles import Style

        style = Style.from_dict({
            "": "#00ffff bold",
            "prompt": "#00ffff bold",
        })

        result = pt_prompt(
            FormattedText([("class:prompt", prompt_text)]),
            style=style,
            multiline=False,
        )
        return result.strip() or default
    except Exception:
        pass

    # fallback: 内置 input()
    try:
        import sys
        if sys.platform == "win32":
            import os
            os.system("")  # Windows: 启用 ANSI 转义序列
        result = input(prompt_text)
        return result.strip() or default
    except (EOFError, KeyboardInterrupt):
        raise


# ── Web 模式检测 ─────────────────────────────────────────

def _check_web_mode() -> bool:
    """检测是否处于 Web/suspension 模式。"""
    try:
        from data_agent.agent.loop import get_interaction_mode
        return get_interaction_mode() == "web"
    except ImportError:
        return False


# ── 单问题交互 ───────────────────────────────────────────

def _display_question(
    question_text: str,
    options: list[dict],
    preview: str = "",
    question_num: Optional[int] = None,
    total_questions: Optional[int] = None,
) -> None:
    """渲染一个问题的可视化展示。"""
    # 问题标题
    prefix = ""
    if question_num is not None and total_questions is not None and total_questions > 1:
        prefix = f"[{question_num}/{total_questions}] "

    header = Text()
    header.append("? ", style="bold yellow")
    header.append(f"{prefix}{question_text}", style="bold")
    console.print(Panel(header, border_style="yellow", padding=(0, 1)))

    # 预览内容
    if preview:
        console.print()
        console.print(Panel(preview, title="Preview", border_style="dim", padding=(0, 1)))

    # 选项列表
    if options:
        console.print()
        for i, opt in enumerate(options):
            label = opt.get("label", str(opt)) if isinstance(opt, dict) else str(opt)
            desc = opt.get("description", "") if isinstance(opt, dict) else ""

            line = Text()
            line.append(f"  {i + 1}. ", style="bold cyan")
            line.append(label, style="bold green")
            if desc:
                line.append(f"  — {desc}", style="dim")
            console.print(line)


def _get_input_hint(options: list[dict], multi_select: bool) -> str:
    """根据选项和模式返回输入提示文本。"""
    if multi_select and options:
        return "输入编号（逗号分隔），或直接输入回答。Enter 跳过"
    elif options:
        return "输入编号选择，或直接输入回答。Enter 跳过"
    else:
        return "请输入您的回答。Enter 跳过"


def _process_answer(answer: str, options: list[dict], multi_select: bool) -> dict:
    """处理用户回答，返回结构化结果。"""
    # 跳过
    if not answer or answer.lower() in ("skip", "跳过"):
        return {"answer": "skipped", "selected_option": None, "is_free_input": False}

    # 取消
    if answer.lower() in ("cancel", "cancelled", "取消", "q", "quit"):
        return {"answer": "cancelled", "selected_option": None, "is_free_input": False}

    # 多选模式
    if multi_select and options:
        parts = [p.strip() for p in answer.split(",")]
        selected_indices = []
        free_answers = []

        for part in parts:
            if part.isdigit():
                idx = int(part) - 1
                if 0 <= idx < len(options):
                    selected_indices.append(idx)
                else:
                    free_answers.append(part)
            else:
                free_answers.append(part)

        if selected_indices:
            selected_labels = []
            selected_items = []
            for idx in selected_indices:
                sel = options[idx]
                label = sel.get("label", str(sel)) if isinstance(sel, dict) else str(sel)
                selected_labels.append(label)
                selected_items.append(sel)
                console.print(f"  [green]✓ {label}[/green]")

            return {
                "answer": ", ".join(selected_labels),
                "selected_options": selected_items,
                "is_free_input": False,
                "multi_select": True,
            }

        if free_answers:
            joined = ", ".join(free_answers)
            console.print(f"  [green]→ {joined}[/green]")
            return {
                "answer": joined,
                "selected_option": None,
                "is_free_input": True,
                "multi_select": True,
            }

    # 单选模式：数字匹配选项
    if options and answer.isdigit():
        idx = int(answer) - 1
        if 0 <= idx < len(options):
            selected = options[idx]
            label = selected.get("label", str(selected)) if isinstance(selected, dict) else str(selected)
            console.print(f"  [green]✓ {label}[/green]")
            return {
                "answer": label,
                "selected_option": selected,
                "is_free_input": False,
            }

    # 自由输入
    console.print(f"  [green]→ {answer}[/green]")
    return {
        "answer": answer,
        "selected_option": None,
        "is_free_input": True,
    }


def _ask_single(
    question_text: str,
    options: list[dict],
    multi_select: bool = False,
    preview: str = "",
    question_num: Optional[int] = None,
    total_questions: Optional[int] = None,
) -> dict:
    """交互式提问单个问题并获取回答。

    Returns:
        dict with keys: answer, selected_option/selected_options, is_free_input, multi_select
    """
    console.print()
    _display_question(question_text, options, preview, question_num, total_questions)

    # 输入提示区
    hint = _get_input_hint(options, multi_select)
    console.print()
    console.print(Panel(
        f"[dim]{hint}[/dim]",
        border_style="dim cyan",
        padding=(0, 1),
    ))

    # 获取输入
    try:
        answer = _robust_input("  >> ")
    except (EOFError, KeyboardInterrupt):
        console.print("  [dim]已取消[/dim]")
        return {"answer": "cancelled", "selected_option": None, "is_free_input": False}

    return _process_answer(answer, options, multi_select)


# ── 多问题交互 ───────────────────────────────────────────

def _ask_multiple(questions: list[dict]) -> dict:
    """依次提出多个问题，收集所有回答。

    Args:
        questions: [{"question": "...", "options": [...], "multi_select": false, "preview": ""}]

    Returns:
        {"answers": [...], "count": N}
    """
    total = len(questions)
    answers = []

    # 总览
    console.print()
    overview = Text()
    overview.append(f"📋 共 {total} 个问题需要确认", style="bold cyan")
    console.print(Panel(overview, border_style="cyan", padding=(0, 1)))

    for i, q in enumerate(questions):
        q_text = q.get("question", "")
        q_options = q.get("options", [])
        q_multi = q.get("multi_select", False)
        q_preview = q.get("preview", "")

        result = _ask_single(
            question_text=q_text,
            options=q_options,
            multi_select=q_multi,
            preview=q_preview,
            question_num=i + 1,
            total_questions=total,
        )
        answers.append({
            "question": q_text,
            **result,
        })

    # 汇总
    console.print()
    summary_parts = []
    for i, ans in enumerate(answers):
        summary_parts.append(f"  Q{i + 1}: {ans.get('answer', 'skipped')}")
    summary_text = "\n".join(summary_parts)
    console.print(Panel(
        f"[bold]提交的回答：[/]\n{summary_text}",
        border_style="green",
        padding=(0, 1),
    ))

    return {
        "answers": answers,
        "count": total,
    }


# ── 工具注册 ─────────────────────────────────────────────

@registry.register(
    name="ask_user_question",
    description=(
        "在分析关键节点向用户提问，获取确认或选择。"
        "必须使用的场景：(1) 影响分析准确度的歧义（指标名、时间范围、数据含义）"
        "(2) LLM 无法判断正确性（数据异常是业务正常还是错误、分析结果与预期不符）"
        "(3) 无法理解的内容（业务术语、特殊字段含义、非标准数据格式）。"
        "支持单问题（question + options）和多问题（questions JSON 数组）两种模式。"
        "\n\n单问题模式：question='分析方向？', options='[{\"label\": \"A. 趋势\", \"description\": \"...\"}, ...]'"
        "\n多问题模式（需同时确认多个参数时使用）："
        "questions='[{\"question\": \"时间范围？\", \"options\": [{\"label\": \"全部\", \"description\": \"...\"}, {\"label\": \"近30天\", \"description\": \"...\"}]}, "
        "{\"question\": \"关注指标？\", \"options\": [{\"label\": \"收入\", \"description\": \"...\"}, {\"label\": \"留存\", \"description\": \"...\"}], \"multi_select\": true}]'"
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "要问的问题（单问题模式使用）",
            },
            "options": {
                "type": "string",
                "description": (
                    '预置选项，JSON 数组格式: [{"label": "...", "description": "..."}]。'
                    "至少提供 2 个选项，最多 4 个。单问题模式使用。"
                ),
            },
            "multi_select": {
                "type": "boolean",
                "description": "是否允许多选（默认 false）。单问题模式使用。",
            },
            "preview": {
                "type": "string",
                "description": "选项的补充预览内容（可选），帮助用户对比选项差异",
            },
            "questions": {
                "type": "string",
                "description": (
                    "多问题模式：JSON 数组格式，最多 4 个问题。"
                    '格式: [{"question": "...", "options": [{"label": "...", "description": "..."}], '
                    '"multi_select": false}]'
                    "。提供 questions 时忽略 question/options/multi_select 参数。"
                ),
            },
            "confirmation_type": {
                "type": "string",
                "description": "结构化确认类型：scope_confirmation/data_requirement_confirmation/method_confirmation/data_quality_confirmation/follow_up_choice",
            },
            "blocking_reason": {
                "type": "string",
                "description": "为什么需要用户确认；用于 CLI/Web 展示和分析状态记录。",
            },
            "state_updates": {
                "type": "string",
                "description": "用户回答后要合并到 AnalysisSessionState 的 JSON 对象。",
            },
            "related_task_id": {
                "type": "integer",
                "description": "关联的 task id，可选。",
            },
            "related_spec_id": {
                "type": "string",
                "description": "关联的 AnalysisSpec id，可选。",
            },
        },
        "required": [],
    },
)
def ask_user_question(
    question: str = "",
    options: str = "",
    multi_select: bool = False,
    preview: str = "",
    questions: str = "",
    confirmation_type: str = "",
    blocking_reason: str = "",
    state_updates: str = "",
    related_task_id: int = 0,
    related_spec_id: str = "",
) -> str:
    """向用户展示问题并获取回答。支持单问题和多问题模式。"""

    from data_agent.agent.loop import UserConfirmationRequired

    # ── 多问题模式 ──
    if questions:
        try:
            parsed_questions = json.loads(questions)
        except json.JSONDecodeError:
            parsed_questions = []

        if isinstance(parsed_questions, list) and parsed_questions:
            # 限制最多 4 个问题
            parsed_questions = parsed_questions[:3]

            # 统一使用 suspension 模式（CLI 和 Web）
            combined_q = "; ".join(q.get("question", "") for q in parsed_questions)
            all_options = []
            for q in parsed_questions:
                all_options.extend(q.get("options", []))
            raise UserConfirmationRequired(
                question=combined_q,
                options=all_options,
                context=json.dumps(parsed_questions, ensure_ascii=False),
                confirmation_type=confirmation_type,
                blocking_reason=blocking_reason,
                state_updates=state_updates,
                related_task_id=related_task_id,
                related_spec_id=related_spec_id,
            )

    # ── 解析单问题选项 ──
    parsed_options = []
    if options:
        try:
            parsed_options = json.loads(options)
        except json.JSONDecodeError:
            parsed_options = [{"label": opt.strip(), "description": ""} for opt in options.split(",")]

    # 统一使用 suspension 模式（CLI 和 Web）
    raise UserConfirmationRequired(
        question=question,
        options=parsed_options,
        context="",
        multi_select=multi_select,
        confirmation_type=confirmation_type,
        blocking_reason=blocking_reason,
        state_updates=state_updates,
        related_task_id=related_task_id,
        related_spec_id=related_spec_id,
    )
