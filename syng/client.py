import asyncio
from traceback import print_exc
from json import load
import logging
from argparse import ArgumentParser

import socketio

from .sources import Source, configure_sources
from .entry import Entry


sio = socketio.AsyncClient()
logger = logging.getLogger(__name__)
sources: dict[str, Source] = {}


currentLock = asyncio.Semaphore(0)
state = {
    "current": None,
    "queue": [],
    "room": None,
}


@sio.on("skip")
async def handle_skip():
    logger.info("Skipping current")
    await state["current"].skip_current()


@sio.on("state")
async def handle_state(data):
    state["queue"] = [Entry(**entry) for entry in data]


@sio.on("connect")
async def handle_connect():
    logging.info("Connected to server")
    await sio.emit(
        "register-client",
        {
            "secret": "test",
            "queue": [entry.to_dict() for entry in state["queue"]],
            "room": state["room"],
        },
    )


@sio.on("buffer")
async def handle_buffer(data):
    source = sources[data["source"]]
    meta_info = await source.buffer(Entry(**data))
    await sio.emit("meta-info", {"uuid": data["uuid"], "meta": meta_info})


@sio.on("play")
async def handle_play(data):
    entry = Entry(**data)
    logging.info("Playing %s", entry)
    try:
        meta_info = await sources[entry.source].buffer(entry)
        await sio.emit("meta-info", {"uuid": data["uuid"], "meta": meta_info})
        state["current"] = sources[entry.source]
        await sources[entry.source].play(entry)
    except Exception:
        print_exc()
    logging.info("Finished, waiting for next")
    await sio.emit("pop-then-get-next")


@sio.on("client-registered")
async def handle_register(data):
    if data["success"]:
        logging.info("Registered")
        print(f"Join using code: {data['room']}")
        state["room"] = data["room"]
        await sio.emit("sources", {"sources": list(sources.keys())})
        if state["current"] is None:
            await sio.emit("get-first")
    else:
        logging.warning("Registration failed")
        await sio.disconnect()


@sio.on("request-config")
async def handle_request_config(data):
    if data["source"] in sources:
        config = await sources[data["source"]].get_config()
        if isinstance(config, list):
            num_chunks = len(config)
            for current, chunk in enumerate(config):
                await sio.emit(
                    "config-chunk",
                    {
                        "source": data["source"],
                        "config": chunk,
                        "number": current + 1,
                        "total": num_chunks,
                    },
                )
        else:
            await sio.emit("config", {"source": data["source"], "config": config})


async def main():
    parser = ArgumentParser()

    parser.add_argument("--room", "-r")
    parser.add_argument("config")

    args = parser.parse_args()

    with open(args.config, encoding="utf8") as file:
        source_config = load(file)
    sources.update(configure_sources(source_config))
    if args.room:
        state["room"] = args.room

    await sio.connect("http://127.0.0.1:8080")
    await sio.wait()


if __name__ == "__main__":
    asyncio.run(main())
