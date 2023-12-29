from sys import version as sys_version
from string import ascii_letters
from random import choice


def random_string(length: int):
    characters = ascii_letters
    return "".join(choice(characters) for _ in range(length))


platform = "terminal"
appid_prefix = "b875bf44863911ee"  # 16B
appid = appid_prefix + random_string(48)

version = sys_version
py_ver = version[: version.find(" ")]
gcc_ver = version[version.find("\n") + 2 : -1]
user_agent = f"Python {py_ver} / {gcc_ver}"
