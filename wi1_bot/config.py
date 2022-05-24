import yaml

with open("config.yaml", "rb") as f:
    config = yaml.load(f, Loader=yaml.SafeLoader)
