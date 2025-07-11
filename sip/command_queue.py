import logging
import queue
from typing import Any, Dict

_cmd_q: "queue.Queue[tuple[str, Dict[str, Any]]]" = queue.Queue()

def queue_command(cmd: str, **kwargs):
    """Безопасно кладёт команду для исполнения в главном потоке."""
    _cmd_q.put((cmd, kwargs), block=False)

def process_command_queue():
    """Вызывается из главного потока. Исполняет команды агента."""
    from .call import Call  # локальный импорт, чтобы избежать циклов
    import pjsua2 as pj
    while not _cmd_q.empty():
        cmd, kw = _cmd_q.get_nowait()
        if cmd == "hangup" and Call.current:
            try:
                prm = pj.CallOpParam()
                if "statusCode" in kw:
                    prm.statusCode = kw["statusCode"]
                Call.current.hangup(prm)
                logging.info(f"[PJSUA] Успешный сброс вызова ({kw.get('reason','')})")
            except Exception as e:
                logging.error(f"[PJSUA] Ошибка сброса вызова: {e}")
        _cmd_q.task_done()