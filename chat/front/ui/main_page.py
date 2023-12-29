from asyncio import StreamReader

from base.page import BasePage, Quit, ctrl_map
from base.app import BaseApp
from utils.terminal import readline
from models.message import MessageStore

main = (
    "Welcome to chatApp\n"
    "You can choose something: \n"
    "1.chat sessions\n"
    "2.friends\n"
)

main_store = MessageStore(1, main)


class MainPage(BasePage):
    def __init__(self, name: str, store: MessageStore):
        super().__init__(name, store)

    def bind(self, app: BaseApp):
        self.app = app

        routes = app.routes
        self.hooks = {
            "1\n": routes["chat_page"],
            "2\n": routes["friend_page"],
        }

    async def interaction(self, reader: StreamReader):
        selection = await readline(reader)
        ctrl = ctrl_map.get(selection)
        if ctrl is not None:
            return Quit

        route = self.hooks.get(selection)
        if route is None:
            raise Exception("Interface Error: wrong seletion")

        return route
