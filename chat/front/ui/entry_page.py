from asyncio import StreamReader

from base.app import BaseApp
from base.page import BasePage, Quit, ctrl_map
from utils.terminal import readline
from models.message import MessageStore


entry = "Login or Register, give your selection:\n" "1. Login\n" "2. Register\n"

entry_store = MessageStore(1, entry)


class EntryPage(BasePage):
    def __init__(self, name: str, store: MessageStore):
        super().__init__(name, store)

    async def interaction(self, reader: StreamReader):
        app: BaseApp = self.app
        selection = await readline(reader)
        if selection == "1\n":
            return app.routes["login_page"]
        elif selection == "2\n":
            return app.routes["register_page"]
        else:
            ctrl = ctrl_map.get(selection)
            if ctrl is not None:
                return Quit
            raise Exception("Interface Error: wrong seletion")
