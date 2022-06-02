import asyncio
import json

from websockets.exceptions import ConnectionClosedError
from websockets.legacy.protocol import broadcast as ws_broadcast
from websockets.server import WebSocketServerProtocol
from websockets.server import serve as ws_serve


class Websocket:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.event_loop = loop

        self.connections: set[WebSocketServerProtocol] = set()
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.current_log: list[str] = []

    def put(self, item: str) -> None:
        asyncio.run_coroutine_threadsafe(self.queue.put(item), self.event_loop)

    async def start(self) -> None:
        async with ws_serve(self.register, "localhost", 9001):
            await self.worker()  # runs forever

    async def register(self, ws: WebSocketServerProtocol) -> None:
        await ws.send(json.dumps({"type": "log", "data": self.current_log}))

        self.connections.add(ws)

        try:
            await ws.wait_closed()
        except ConnectionClosedError:
            pass
        finally:
            self.connections.remove(ws)

    async def worker(self) -> None:
        while True:
            item = await self.queue.get()

            if item == "DONE":
                self.current_log = []
                continue

            self.current_log.append(item)

            ws_broadcast(self.connections, json.dumps({"type": "update", "data": item}))
