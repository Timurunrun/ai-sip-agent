import logging
import signal
import queue
import os
from config import load_config
from sip.endpoint import create_endpoint
from sip.account import Account
from crm.crm_api import enrich_funnel_config_with_crm
from llm.agent import init_llm_agent_tts_queue
from stt.deepgram_stt import init_interjection_tts_queue

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    config = load_config()
    sip_event_queue = queue.Queue()
    sip_event_queue.current_call = None  # текущий звонок (monkey-patch)
    sip_event_queue.config = config
    
    tts_playback_queue = queue.Queue()
    init_llm_agent_tts_queue(tts_playback_queue)
    init_interjection_tts_queue(tts_playback_queue)
    
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
                tts_file_to_play = tts_playback_queue.get_nowait()
                if tts_file_to_play:
                    logging.info(f"[Main-Debug] Попытка воспроизвести TTS. Файл: {tts_file_to_play}. Текущий звонок: {sip_event_queue.current_call}")
                    current_call_instance = sip_event_queue.current_call
                    if current_call_instance and hasattr(current_call_instance, 'play_wav'):
                        abs_tts_file_path = os.path.abspath(tts_file_to_play)
                        logging.info(f"[Main] Проигрывается TTS файл: {abs_tts_file_path} для звонка {current_call_instance}")
                        current_call_instance.play_wav(abs_tts_file_path)
                    elif not current_call_instance:
                        logging.warning(f"[Main] Нет активного звонка для проигрывания TTS файла: {tts_file_to_play}")
                    else:
                        logging.warning(f"[Main] Экземпляр current_call не имеет метода play_wav или не является корректным объектом звонка.")
            except queue.Empty:
                pass
            except Exception as e:
                logging.error(f"[Main] Ошибка при проигрывании TTS аудио: {e}", exc_info=True)

            # Маленькая пауза для экономии CPU
            time.sleep(0.05)

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
    main()