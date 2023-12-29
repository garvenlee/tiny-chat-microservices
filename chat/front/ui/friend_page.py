from asyncio import StreamReader

from base.page import BasePage, ctrl_map
from base.app import BaseApp
from utils.terminal import readline
from models.message import MessageStore

friend = (
    "Allow the following friend-related operations:\n"
    "1.add_new_friend\n"
    "2.friend_action_history\n"
    "3.friend_list\n"
)
friend_store = MessageStore(10, initial=friend)  # max 1000 friends


class FriendPage(BasePage):
    def __init__(self, name: str, store: MessageStore):
        super().__init__(name, store)

    def bind(self, app: BaseApp):
        self.app = app

        routes = app.routes
        self.hooks = {
            "1\n": routes["add_friend_page"],
            "2\n": routes["friend_action_history_page"],
            "3\n": routes["friend_list"],
        }

    async def interaction(self, reader: StreamReader):
        selection = await readline(reader)
        ctrl = ctrl_map.get(selection)
        if ctrl is not None:
            return ctrl

        route = self.hooks.get(selection)
        if route is None:
            raise Exception("Interface Error: wrong seletion")

        return route
