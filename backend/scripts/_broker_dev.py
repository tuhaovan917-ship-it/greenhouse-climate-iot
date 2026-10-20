"""Throwaway MQTT broker for local integration checks (dev dependency only).

Usage: python _broker_dev.py [port]
"""

import asyncio
import sys

from amqtt.broker import Broker

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 1895


async def main() -> None:
    broker = Broker(
        {
            "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{PORT}"}},
            "sys_interval": 0,
            "auth": {"allow-anonymous": True},
        }
    )
    await broker.start()
    print(f"broker ready on {PORT}", flush=True)
    while True:
        await asyncio.sleep(3600)


asyncio.run(main())
