"""Shared helpers for the Radarr/Sonarr e2e seed regeneration scripts.

Both *arrs are seeded the same way: boot a fresh, pinned container with a fixed API key,
configure it via the v3 API (root folder, quality profile, one library item, and an On
Import webhook Connect), then snapshot ``config.xml`` + the app DB. Radarr connection-tests
a webhook on create, so a throwaway server aliased ``wi1-bot-webhook`` runs on a shared
network for the duration.
"""

import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

import requests

# keep in sync with tests/e2e/config/webhook.yaml and the seeds' config.xml
API_KEY = "0123456789abcdef0123456789abcdef"
WEBHOOK_HOST = "wi1-bot-webhook"  # matches the compose service the real webhook runs as
WEBHOOK_URL = f"http://{WEBHOOK_HOST}:9000/"

SEED_NETWORK = "wi1bot-e2e-seed-net"
WEBHOOK_CONTAINER = "wi1bot-e2e-webhook-seed"
WHOAMI_IMAGE = "traefik/whoami:latest"  # returns 200 to any method, so the webhook test passes


def config_xml(instance_name: str, port: int) -> str:
    return f"""<Config>
  <BindAddress>*</BindAddress>
  <Port>{port}</Port>
  <SslPort>9898</SslPort>
  <EnableSsl>False</EnableSsl>
  <ApiKey>{API_KEY}</ApiKey>
  <AuthenticationMethod>External</AuthenticationMethod>
  <AuthenticationRequired>DisabledForLocalAddresses</AuthenticationRequired>
  <Branch>master</Branch>
  <LogLevel>info</LogLevel>
  <InstanceName>{instance_name}</InstanceName>
  <UrlBase></UrlBase>
</Config>
"""


def run_docker(*args: str, check: bool = True) -> None:
    subprocess.run(["docker", *args], check=check, capture_output=True, text=True)


def start_seed_network() -> None:
    run_docker("network", "create", SEED_NETWORK)
    run_docker(
        "run", "-d", "--name", WEBHOOK_CONTAINER,
        "--network", SEED_NETWORK, "--network-alias", WEBHOOK_HOST,
        WHOAMI_IMAGE, "--port", "9000",
    )  # fmt: skip


def teardown_seed_network(*containers: str) -> None:
    run_docker("rm", "-f", WEBHOOK_CONTAINER, *containers, check=False)
    run_docker("network", "rm", SEED_NETWORK, check=False)


def start_arr(
    container: str,
    image: str,
    host_port: int,
    internal_port: int,
    config_dir: Path,
    media_dir: Path,
) -> None:
    run_docker(
        "run", "-d", "--name", container, "--network", SEED_NETWORK,
        "-e", "PUID=0", "-e", "PGID=0", "-e", "UMASK=000", "-e", "TZ=Etc/UTC",
        "-p", f"{host_port}:{internal_port}",
        "-v", f"{config_dir}:/config",
        "-v", f"{media_dir}:/media",
        image,
    )  # fmt: skip


def snapshot(config_dir: Path, seed_dir: Path, db_name: str) -> None:
    """Copy config.xml + the app DB into the committed seed dir.

    The *arr shutdown doesn't reliably checkpoint the SQLite WAL, so the last writes
    (e.g. the webhook Connect) can be stranded in the ``-wal`` file. Merge it into the
    main DB first so a ``.db``-only snapshot is complete.
    """
    db_path = config_dir / db_name
    if not db_path.exists():
        raise RuntimeError(f"expected {db_path} to exist after shutdown")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()

    if seed_dir.exists():
        shutil.rmtree(seed_dir)
    seed_dir.mkdir(parents=True)
    for name in ("config.xml", db_name):
        src = config_dir / name
        if not src.exists():
            raise RuntimeError(f"expected {src} to exist after shutdown")
        shutil.copy2(src, seed_dir / name)


class ArrApi:
    """Thin Radarr/Sonarr v3 API client (both share the same endpoints used here)."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"X-Api-Key": API_KEY})

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        resp = self.session.request(method, f"{self.base_url}{path}", timeout=30, **kwargs)
        if not resp.ok:
            raise RuntimeError(f"{method} {path} -> {resp.status_code}: {resp.text}")
        return resp

    def wait_ready(self, timeout: float = 180.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if (
                    self.session.get(f"{self.base_url}/api/v3/system/status", timeout=5).status_code
                    == 200
                ):
                    return
            except requests.RequestException:
                pass
            time.sleep(2)
        raise TimeoutError(f"{self.base_url} API did not become available in time")

    def quality_profile_id(self, name: str) -> int:
        profiles = self.request("GET", "/api/v3/qualityprofile").json()
        profile = next((p for p in profiles if p["name"] == name), None)
        if profile is None:
            have = ", ".join(sorted(p["name"] for p in profiles))
            raise RuntimeError(f"no default quality profile named {name!r} (have: {have})")
        return int(profile["id"])

    def add_webhook_notification(self) -> None:
        schema = self.request("GET", "/api/v3/notification/schema").json()
        webhook = next(s for s in schema if s["implementation"] == "Webhook")
        for field in webhook.get("fields", []):
            if field["name"] == "url":
                field["value"] = WEBHOOK_URL
            elif field["name"] == "method":
                field["value"] = 1  # POST
        webhook.update(
            {
                "name": "e2e-webhook",
                "onGrab": False,
                "onDownload": True,  # "On Import"
                "onUpgrade": True,
                "onRename": False,
                "onHealthIssue": False,
                "onApplicationUpdate": False,
                "tags": [],
            }
        )
        # forceSave has no effect on create in current *arrs, so the throwaway webhook
        # stand-in (start_seed_network) is what lets this connection test pass
        self.request("POST", "/api/v3/notification", json=webhook)

        # confirm it persisted (guards against a silently-dropped create)
        if not self.request("GET", "/api/v3/notification").json():
            raise RuntimeError("webhook notification was not saved")
