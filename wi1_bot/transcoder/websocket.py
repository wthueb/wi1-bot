import asyncio
import json

from websockets.legacy.protocol import broadcast as ws_broadcast
from websockets.server import WebSocketServerProtocol
from websockets.server import serve as ws_serve


class Websocket:
    def __init__(self, output_queue: asyncio.Queue[str]) -> None:
        self.connections: set[WebSocketServerProtocol] = set()
        self.queue = output_queue
        self.current_log: list[str] = []
        self.lock = asyncio.Lock()

    async def start(self) -> None:
        async with ws_serve(self.register, "localhost", 9001):
            await self.worker()

    async def register(self, ws: WebSocketServerProtocol) -> None:
        async with self.lock:
            await ws.send(json.dumps({"type": "log", "data": self.current_log}))

            self.connections.add(ws)

        try:
            await ws.wait_closed()
        finally:
            self.connections.remove(ws)

    async def worker(self) -> None:
        while True:
            item = await self.queue.get()

            async with self.lock:
                if item == "DONE":
                    self.current_log = []
                    continue

                self.current_log.append(item)

                ws_broadcast(
                    self.connections, json.dumps({"type": "update", "data": item})
                )
