from queue import SimpleQueue

from websockets.legacy.protocol import broadcast as ws_broadcast
from websockets.server import WebSocketServerProtocol
from websockets.server import serve as ws_serve

ws_connections: set[WebSocketServerProtocol] = set()


async def start_ws(output_queue: SimpleQueue) -> None:
    async def register(ws: WebSocketServerProtocol) -> None:
        ws_connections.add(ws)

        try:
            await ws.wait_closed()
        finally:
            ws_connections.remove(ws)

    async def loop() -> None:
        while True:
            item = output_queue.get()
            ws_broadcast(ws_connections, str(item))

    async with ws_serve(register, "localhost", 9001):
        await loop()
