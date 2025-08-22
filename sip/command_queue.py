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
        if cmd in ("hangup", "hangup_after_playback") and Call.current:
            try:
                if cmd == "hangup":
                    prm = pj.CallOpParam()
                    if "statusCode" in kw:
                        prm.statusCode = kw["statusCode"]
                    Call.current.hangup(prm)
                    logging.info(f"[PJSUA] Успешный сброс вызова ({kw.get('reason','')})")
                else:  # hangup_after_playback
                    Call.current.request_hangup_after_playback(kw.get('reason',''), immediate=kw.get('immediate', False))
                    logging.info(f"[PJSUA] Отложенный сброс вызова запрошен ({kw.get('reason','')})")
            except Exception as e:
                logging.error(f"[PJSUA] Ошибка сброса вызова: {e}")
        _cmd_q.task_done()