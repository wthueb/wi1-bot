import asyncio

from websockets.legacy.protocol import broadcast as ws_broadcast
from websockets.server import WebSocketServerProtocol
from websockets.server import serve as ws_serve


class Websocket:
    def __init__(self, output_queue: asyncio.Queue) -> None:
        self.connections: set[WebSocketServerProtocol] = set()
        self.queue = output_queue

    async def start(self) -> None:
        async with ws_serve(self.register, "localhost", 9001):
            await self.worker()

    async def register(self, ws: WebSocketServerProtocol) -> None:
        self.connections.add(ws)

        try:
            await ws.wait_closed()
        finally:
            self.connections.remove(ws)

    async def worker(self) -> None:
        while True:
            item = await self.queue.get()
            ws_broadcast(self.connections, str(item))
