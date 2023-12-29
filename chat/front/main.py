from app import ChatApp
from utils.terminal import create_stdin_reader


async def main():
    async with create_stdin_reader() as reader:
        app = ChatApp()

        from routes import routes

        app.bind(routes)
        connection_args = {
            "http_host": "127.0.0.1",
            "http_port": 10000,
            "ws_host": "127.0.0.1",
            "ws_port": 9999,
        }
        await app.initialize(**connection_args)
        await app.run(reader)


if __name__ == "__main__":
    from asyncio import run
    import uvloop

    uvloop.install()
    run(main(), debug=False)
