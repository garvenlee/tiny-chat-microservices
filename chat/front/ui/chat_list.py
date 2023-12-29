from asyncio import StreamReader

from base.app import BaseApp
from base.page import BasePage, ctrl_map
from models.message import MessageStore
from utils.terminal import readline

chat_list = (
    "0.You can choose to add new friend: \n"
    "----------------------------------------------------\n"
    "The following is your friends list:\n"
)
chat_list_store = MessageStore(10000, initial=chat_list)  # max 1000 friends


class ChatListPage(BasePage):
    def __init__(self, name: str, store: MessageStore):
        super().__init__(name, store)

    async def interaction(self, reader: StreamReader):
        app: BaseApp = self.app

        selection = await readline(reader)
        ctrl = ctrl_map.get(selection)
        if ctrl is not None:
            return ctrl
        else:
            raise Exception("Interface Error: wrong seletion")
