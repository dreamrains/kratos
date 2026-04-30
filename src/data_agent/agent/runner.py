"""后台线程执行 Agent turn，支持协作式中断。"""

from __future__ import annotations

import threading
from typing import Optional

from data_agent.utils.logging import get_logger

logger = get_logger("runner")


class AgentRunner:
    """在后台线程执行 agent turn，支持通过 interrupt() 中断。

    中断是协作式的：
    - LLM API 调用无法中途取消（通常 <30s 自然返回）
    - 在工具调用之间检查中断信号
    - 中断后保留已有对话状态
    """

    def __init__(self, loop):
        self._loop = loop
        self._interrupt_event = threading.Event()
        self._result: Optional[str] = None
        self._error: Optional[Exception] = None
        self._running = threading.Event()

    def run_turn(self, user_input: str, timeout: float = 300) -> Optional[str]:
        """在后台线程运行 turn，阻塞等待结果或超时。

        Returns:
            str: 正常完成的回复
            None: 被中断或超时
        """
        self._interrupt_event.clear()
        self._result = None
        self._error = None
        self._running.set()

        thread = threading.Thread(target=self._run, args=(user_input,), daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            self._interrupt_event.set()
            thread.join(timeout=5)
            self._running.clear()
            return None

        self._running.clear()

        if self._error is not None:
            raise self._error

        return self._result

    def interrupt(self) -> None:
        """从主线程发送中断信号。"""
        self._interrupt_event.set()
        logger.info("Interrupt requested")

    def is_running(self) -> bool:
        return self._running.is_set()

    def _run(self, user_input: str) -> None:
        try:
            self._result = self._loop.run_turn(user_input)
        except Exception as e:
            self._error = e
