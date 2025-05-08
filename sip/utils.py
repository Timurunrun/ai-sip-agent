def get_active_lead_id():
    """Возвращает ID текущей активной сделки из очереди событий"""
    import sip.call
    if sip.call.Call.current and hasattr(sip.call.Call.current.acc.sip_event_queue, 'config'):
        return sip.call.Call.current.acc.sip_event_queue.config.get('ACTIVE_LEAD_ID') 