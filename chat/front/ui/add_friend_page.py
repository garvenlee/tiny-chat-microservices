from asyncio import StreamReader

from base.app import BaseApp
from base.page import BasePage, Quit, Back, quit_tag, back_tag, ctrl_map
from base.status_bar import NotificationType

from models.message import MessageStore
from network.http import SUCCESS, NOT_FOUND
from utils.terminal import readline


friend = "> Add new friend\n" "Enter new friend's email: "
add_friend_store = MessageStore(1000, initial=friend)  # max 1000 friends


class AddFriendPage(BasePage):
    def __init__(self, name: str, store: MessageStore):
        super().__init__(name, store)

    async def interaction(self, reader: StreamReader):
        app: BaseApp = self.app
        store = self.store
        session = app.active_user_session

        show_notification_in_duration = app.status_bar.show_notification_in_duration
        while True:
            offset = 0
            email: str = await readline(reader)
            ctrl = ctrl_map.get(email)
            if ctrl is not None:
                return ctrl

            store.append(email)
            offset += 1
            self.redraw_output()

            email = email.strip()
            # check if this email has in own friends list or just is self.
            user = session.check_before_query_user(email)
            if user is not None:
                store.append(f"Oh, user {email} is already in your friend list.\n\n")
                offset += 1
                self.redraw_output()
            else:
                user, status = await session.query_user(email)
                if status is SUCCESS:
                    info_string = (
                        f"Yes, we found this user: {email}.\n\n"
                        "> Now you can type `add` to send a friend request to this user.\n"
                        "\tor choose `quit` or `back` to exit this page.\n\n"
                    )
                    store.append(info_string)
                    offset += 1

                    self.redraw_output()

                    if (stdin := await readline(reader)) == back_tag:
                        store.restore()
                        return Back
                    elif stdin == quit_tag:
                        return Quit
                    elif stdin == "add\n":
                        info_string = "> You can decide to attach some request_message below(`\\n`: ignore)\n"
                        store.append(info_string)
                        offset += 1

                        self.redraw_output()

                        request_message: str = await readline(reader)
                        if request_message == "\n":
                            request_message = None
                        else:
                            request_message = request_message.strip()

                        # TODO recheck: this blocks ui
                        status = await session.add_friend(user.seq, request_message)
                        if status is SUCCESS:
                            session.write_local_friend_request(user, request_message)
                            show_notification_in_duration(
                                f"Hey, you have sent the friend request to {email}",
                                NotificationType.INFO,
                                timeout=3,
                            )
                        else:  # timeout or failed
                            show_notification_in_duration(
                                "Found timeout in SendFriendRequest, maybe try later",
                                NotificationType.WARNING,
                                timeout=3,
                            )
                    else:
                        raise Exception()

                elif status is NOT_FOUND:
                    info_string = f"\tUser {email} does not exist, please check it.\n\n"
                    store.append(info_string)
                    offset += 1
                else:
                    show_notification_in_duration(
                        "Found timeout in UserQuery, maybe try later",
                        NotificationType.WARNING,
                        timeout=3,
                    )

            store.append(
                "> Now you can choose `quit` or `back` to exit this page, \n"
                "\tor type anything else to add new friend again...\n"
            )
            offset += 1
            self.redraw_output()

            stdin: str = await readline(reader)
            if stdin == back_tag:
                store.restore()
                return Back
            elif stdin == quit_tag:
                return Quit
            else:
                self.reset(offset)
                self.redraw_output()
