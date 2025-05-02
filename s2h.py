import asyncio
import logging
import argparse
import time
from collections import defaultdict
from contextlib import suppress

# Use uvloop for better performance (optional)
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

# Configure logging
logging.basicConfig(level=logging.WARNING, format='[%(asctime)s] %(levelname)s - %(message)s')
logging.getLogger("asyncio").setLevel(logging.ERROR)  # suppress noisy asyncio errors

class ConnectionPool:
    def __init__(self, max_idle=10, idle_timeout=300):
        self.pool = defaultdict(list)  # key -> list of (reader, writer, timestamp)
        self.locks = defaultdict(asyncio.Lock)
        self.max_idle = max_idle
        self.idle_timeout = idle_timeout

    async def get_connection(self, host, port):
        key = (host, port)
        async with self.locks[key]:
            while self.pool[key]:
                reader, writer, ts = self.pool[key].pop(0)
                if writer.is_closing():
                    continue
                return reader, writer
            return await asyncio.open_connection(host, port)

    async def release_connection(self, host, port, reader, writer):
        key = (host, port)
        async with self.locks[key]:
            if writer.is_closing():
                return
            if len(self.pool[key]) >= self.max_idle:
                writer.close()
                await writer.wait_closed()
            else:
                self.pool[key].append((reader, writer, time.time()))

    async def reap_idle(self):
        while True:
            now = time.time()
            for key, conns in list(self.pool.items()):
                self.pool[key] = [
                    (r, w, ts) for (r, w, ts) in conns if now - ts < self.idle_timeout and not w.is_closing()
                ]
            await asyncio.sleep(self.idle_timeout)

    async def close_all(self):
        for conns in self.pool.values():
            for reader, writer, _ in conns:
                writer.close()
                await writer.wait_closed()

# Global connection pool
connection_pool = ConnectionPool()

async def handle_socks5(reader, writer, proxy_host, proxy_port):
    try:
        # SOCKS5 handshake
        ver = await reader.readexactly(1)
        n_methods = await reader.readexactly(1)
        await reader.readexactly(ord(n_methods))
        writer.write(b"\x05\x00")  # no auth
        await writer.drain()

        # Request
        _, cmd, _, addr_type = await reader.readexactly(4)
        if addr_type == 1:
            raw = await reader.readexactly(4)
            address = ".".join(map(str, raw))
        elif addr_type == 3:
            length = ord(await reader.readexactly(1))
            address = (await reader.readexactly(length)).decode()
        elif addr_type == 4:
            raw = await reader.readexactly(16)
            address = ":".join(f"{raw[i]:02x}{raw[i+1]:02x}" for i in range(0, 16, 2))
        else:
            writer.close()
            await writer.wait_closed()
            return
        port = int.from_bytes(await reader.readexactly(2), 'big')

        # Reply success
        writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        await writer.drain()

        # Tunnel via HTTP proxy
        await tunnel(reader, writer, address, port, proxy_host, proxy_port)
    except Exception:
        pass
    finally:
        with suppress(Exception):
            writer.close()
            await writer.wait_closed()

async def tunnel(client_reader, client_writer, addr, port, proxy_host, proxy_port):
    try:
        proxy_reader, proxy_writer = await connection_pool.get_connection(proxy_host, proxy_port)
        proxy_writer.write(f"CONNECT {addr}:{port} HTTP/1.1\r\nHost: {addr}:{port}\r\n\r\n".encode())
        await proxy_writer.drain()
        header = await proxy_reader.readuntil(b"\r\n\r\n")
        if b"200" not in header:
            proxy_writer.close()
            await proxy_writer.wait_closed()
            return

        async def forward(src, dst):
            try:
                while True:
                    data = await src.read(64 * 1024)
                    if not data:
                        break
                    dst.write(data)
                    await dst.drain()
            except Exception:
                pass
            finally:
                with suppress(Exception):
                    if not dst.is_closing():
                        dst.close()

        await asyncio.gather(
            forward(client_reader, proxy_writer),
            forward(proxy_reader, client_writer)
        )

        await connection_pool.release_connection(proxy_host, proxy_port, proxy_reader, proxy_writer)
    except Exception:
        with suppress(Exception):
            if 'proxy_writer' in locals() and proxy_writer:
                proxy_writer.close()
                await proxy_writer.wait_closed()

async def start(socks_host, socks_port, proxy_host, proxy_port):
    asyncio.create_task(connection_pool.reap_idle())
    server = await asyncio.start_server(
        lambda r, w: handle_socks5(r, w, proxy_host, proxy_port),
        socks_host, socks_port
    )
    addr = server.sockets[0].getsockname()
    logging.warning(f"Listening on {addr}, upstream {proxy_host}:{proxy_port}")
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--socks-host', default='127.0.0.1')
    parser.add_argument('--socks-port', type=int, default=1080)
    parser.add_argument('--proxy-host', required=True)
    parser.add_argument('--proxy-port', type=int, required=True)
    args = parser.parse_args()
    try:
        asyncio.run(start(
            args.socks_host, args.socks_port,
            args.proxy_host, args.proxy_port
        ))
    except KeyboardInterrupt:
        pass
