from ui.entry_page import EntryPage, entry_store
from ui.login_page import LoginPage, login_store
from ui.register_page import RegisterPage, register_store
from ui.main_page import MainPage, main_store
from ui.user_info_page import UserInfoPage, user_info_store
from ui.chat_list import ChatListPage, chat_list_store
from ui.chat_session_page import ChatSessionPage, chat_session_store

from ui.friend_page import FriendPage, friend_store
from ui.friend_action_history import (
    FriendActionHistoryPage,
    friend_action_history_store,
)
from ui.add_friend_page import AddFriendPage, add_friend_store
from ui.friend_list import FriendListPage, friend_list_store

entry_page = EntryPage("Entry", entry_store)
login_page = LoginPage("Login", login_store)
register_page = RegisterPage("Register", register_store)

main_page = MainPage("Main", main_store)
user_info_page = UserInfoPage("UserInfo", user_info_store)
chat_page = ChatListPage("Chat", chat_list_store)
chat_session_page = ChatSessionPage("ChatSession", chat_session_store)

friend_page = FriendPage("Friend", friend_store)
add_friend_page = AddFriendPage("AddFriend", add_friend_store)
friend_action_history_page = FriendActionHistoryPage(
    "FriendActionHistory", friend_action_history_store
)
friend_list_page = FriendListPage("FriendList", friend_list_store)

routes = {
    # user entry
    "entry_page": entry_page,
    "login_page": login_page,
    "register_page": register_page,
    "main_page": main_page,
    "user_info_page": user_info_page,
    # chat related
    "chat_page": chat_page,
    "chat_session_page": chat_session_page,
    # friend related
    "friend_page": friend_page,
    "add_friend_page": add_friend_page,
    "friend_action_history_page": friend_action_history_page,
    "friend_list": friend_list_page,
}
