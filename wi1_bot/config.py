import os

import yaml

_config_path: str | None = None

if os.path.isfile("config.yaml"):
    _config_path = "config.yaml"

if dir := os.getenv("XDG_CONFIG_HOME"):
    if os.path.isfile(os.path.join(dir, "wi1_bot", "config.yaml")):
        _config_path = os.path.join(dir, "wi1_bot", "config.yaml")

if home := os.getenv("HOME"):
    if os.path.isfile(os.path.join(home, ".config", "wi1_bot", "config.yaml")):
        _config_path = os.path.join(home, ".config", "wi1_bot", "config.yaml")

if _config_path is None:
    raise FileNotFoundError(
        "could not find ./config.yaml, $XDG_CONFIG_HOME/wi1_bot/config.yaml or"
        " $HOME/.config/wi1_bot/config.yaml"
    )

with open(_config_path, "r") as f:
    config: dict = yaml.load(f, Loader=yaml.SafeLoader)
