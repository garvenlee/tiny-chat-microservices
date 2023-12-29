from typing import Any


class ServerSetting:
    __slots__ = "setting"

    def __init__(self, setting: dict):
        self.setting = setting

    def get(self, attr: str):
        return self.setting.get(attr)

    def __getattr__(self, __name: str) -> Any:
        return self.setting.get(__name)
