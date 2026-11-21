"""Leitor do chat público da Twitch (IRC oficial, anônimo, só leitura). Sem credenciais."""
from __future__ import annotations

import asyncio
import logging
import random
import ssl
from collections.abc import Callable

log = logging.getLogger("stark.chat")
HOST, PORT = "irc.chat.twitch.tv", 6697
JOINS_PER_10S = 15  # abaixo do limite da Twitch (20 / 10 s)


def parse_privmsg(line: str) -> tuple[str, str] | None:
    """':nick!nick@nick.tmi.twitch.tv PRIVMSG #canal :texto' → (canal, texto)."""
    if " PRIVMSG #" not in line:
        return None
    if line.startswith("@"):  # com tags
        line = line.split(" ", 1)[1] if " " in line else line
    try:
        _, rest = line.split(" PRIVMSG #", 1)
        channel, text = rest.split(" :", 1)
    except ValueError:
        return None
    return channel.strip().lower(), text.strip()


class ChatMonitor:
    def __init__(self, on_message: Callable[[str, str], None]):
        self.on_message = on_message
        self.wanted: set[str] = set()
        self.joined: set[str] = set()
        self.connected = False
        self.error = ""
        self._writer: asyncio.StreamWriter | None = None

    def set_channels(self, channels: set[str]) -> None:
        self.wanted = {c.lower() for c in channels if c}

    async def _send(self, msg: str) -> None:
        if self._writer:
            self._writer.write((msg + "\r\n").encode())
            await self._writer.drain()

    async def _sync_joins(self) -> None:
        while True:
            if self.connected:
                for ch in list(self.joined - self.wanted):
                    await self._send(f"PART #{ch}")
                    self.joined.discard(ch)
                todo = list(self.wanted - self.joined)[:JOINS_PER_10S]
                for ch in todo:
                    await self._send(f"JOIN #{ch}")
                    self.joined.add(ch)
            await asyncio.sleep(10)

    async def run(self) -> None:
        asyncio.create_task(self._sync_joins())
        backoff = 2
        while True:
            try:
                reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(HOST, PORT, ssl=ssl.create_default_context()), 15)
                await self._send("PASS SCHMOOPIIE")
                await self._send(f"NICK justinfan{random.randint(10000, 99999)}")
                self.connected, self.error, self.joined, backoff = True, "", set(), 2
                log.info("chat Twitch conectado")
                while True:
                    raw = await asyncio.wait_for(reader.readline(), 360)
                    if not raw:
                        raise ConnectionError("conexão fechada")
                    line = raw.decode("utf-8", "ignore").rstrip("\r\n")
                    if line.startswith("PING"):
                        await self._send("PONG :tmi.twitch.tv")
                        continue
                    msg = parse_privmsg(line)
                    if msg:
                        self.on_message(*msg)
            except (OSError, asyncio.TimeoutError, ConnectionError) as e:
                self.connected, self.error = False, f"{type(e).__name__}: {e}"[:200]
                log.warning("chat Twitch caiu (%s); reconectando em %ss", self.error, backoff)
                await asyncio.sleep(backoff)
                backoff = min(60, backoff * 2)
