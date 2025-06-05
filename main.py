import logging
import signal
import queue
import os
from config import load_config
from sip.endpoint import create_endpoint
from sip.account import Account
from crm.crm_api import enrich_funnel_config_with_crm

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    config = load_config()
    sip_event_queue = queue.Queue()
    sip_event_queue.current_call = None  # текущий звонок (monkey-patch)
    sip_event_queue.config = config
    
    ep = None
    acc = None
    try:
        ep = create_endpoint()
        acc_cfg = __import__('pjsua2').AccountConfig()
        acc_cfg.idUri = f"sip:{config['SIP_USER']}@{config['SIP_DOMAIN']}"
        acc_cfg.regConfig.registrarUri = f"sip:{config['SIP_DOMAIN']}"
        cred = __import__('pjsua2').AuthCredInfo("digest", "*", config['SIP_USER'], 0, config['SIP_PASSWD'])
        acc_cfg.sipConfig.authCreds.append(cred)
        if config['SIP_PROXY']:
            acc_cfg.sipConfig.proxies.append(config['SIP_PROXY'])
        
        # Очередь для передачи расшифровок из STT
        transcript_queue = queue.Queue()
        acc = Account(sip_event_queue, transcript_queue=transcript_queue)
        acc.create(acc_cfg)
        logging.info("Ждём регистрации SIP-аккаунта...")
        acc.sem_reg.acquire()
        logging.info("SIP-агент запущен и готов к приему звонков. Нажмите Ctrl+C для выхода.")

        import time
        while True:
            try:
                # Обрабатываем очередь аудиофайлов для воспроизведения
                if hasattr(sip_event_queue, 'current_call') and sip_event_queue.current_call:
                    # Импортируем функцию обработки очереди
                    from sip.audio_player import process_audio_queue
                    process_audio_queue()
                    
                    # Проверяем отложенное воспроизведение аудио в текущем звонке
                    sip_event_queue.current_call.check_pending_audio()
            except queue.Empty:
                pass
            except Exception as e:
                pass
            time.sleep(0.1)

    except KeyboardInterrupt:
        logging.info("Выход из программы...")
    except Exception as e:
        logging.error(f"Ошибка Exception: {e}")
    finally:
        if ep:
            try:
                ep.libDestroy()
            except Exception:
                pass

if __name__ == "__main__":
    # Сначала обновляем enriched funnel config через CRM
    enrich_funnel_config_with_crm()
    # Также обновляем enriched post funnel config
    from crm.crm_api import enrich_post_funnel_config_with_crm
    enrich_post_funnel_config_with_crm()
    main()