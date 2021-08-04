from pushover import Client
import yaml


with open('config.yaml', 'rb') as f:
    config = yaml.load(f, Loader=yaml.SafeLoader)

_client = None

if config['pushover']['user_key'] and config['pushover']['api_key']:
    _client = Client(config['pushover']['user_key'], api_token=config['pushover']['api_key'])


def send(msg: str, title: str = None, priority: int = 0) -> None:
    if _client:
        if title:
            _client.send_message(msg, priority=priority, device=config['pushover']['devices'])
        else:
            _client.send_message(msg, title=title, priority=priority,
                                 device=config['pushover']['devices'])
