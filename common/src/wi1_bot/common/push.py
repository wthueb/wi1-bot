import requests

from wi1_bot.common.config import PushoverConfig


def send(
    pushover: PushoverConfig | None,
    msg: str,
    title: str | None = None,
    url: str | None = None,
    priority: int = 0,
) -> None:
    if pushover is None:
        return

    data = {
        "token": pushover.api_key,
        "user": pushover.user_key,
        "message": msg,
        "priority": priority,
        "device": pushover.devices,
    }

    if title is not None:
        data["title"] = title

    if url is not None:
        data["url"] = url

    r = requests.post("https://api.pushover.net/1/messages.json", data=data)

    if not r.ok:
        # TODO: output an error message, maybe use r.raise_for_status(),
        # but would have to handle exceptions from calling code
        pass

    return
