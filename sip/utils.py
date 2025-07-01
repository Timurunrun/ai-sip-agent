def get_active_lead_id(call=None):
    """Возвращает ID текущей активной сделки"""
    if call and hasattr(call.acc.sip_event_queue, 'config'):
        return call.acc.sip_event_queue.config.get('ACTIVE_LEAD_ID')
