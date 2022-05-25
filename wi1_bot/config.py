import os

import yaml

try:
    if os.path.isfile("config.yaml"):
        _config_path = "config.yaml"
    elif dir := os.getenv("XDG_CONFIG_HOME"):
        _config_path = os.path.join(dir, "wi1_bot", "config.yaml")
    elif home := os.getenv("HOME"):
        _config_path = os.path.join(home, ".config", "wi1_bot", "config.yaml")
    else:
        raise FileNotFoundError

    with open(_config_path, "r") as f:
        config = yaml.load(f, Loader=yaml.SafeLoader)
except FileNotFoundError:
    raise FileNotFoundError(
        "could not find config file: put it at ./config.yaml or"
        " $XDG_CONFIG_HOME/wi1_bot/config.yaml"
    )
