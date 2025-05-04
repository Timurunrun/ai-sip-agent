import os
from dotenv import load_dotenv

class ConfigError(Exception):
    pass

def load_config():
    load_dotenv()
    config = {
        'SIP_USER': os.getenv('SIP_USER'),
        'SIP_PASSWD': os.getenv('SIP_PASSWD'),
        'SIP_DOMAIN': os.getenv('SIP_DOMAIN'),
        'SIP_PROXY': os.getenv('SIP_PROXY'),
        'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
        'DEEPGRAM_API_KEY': os.getenv('DEEPGRAM_API_KEY'),
    }
    missing = [k for k, v in config.items() if not v and k != 'SIP_PROXY']
    if missing:
        raise ConfigError(f"Отсутствуют значения конфигурации: {', '.join(missing)}")
    return config
