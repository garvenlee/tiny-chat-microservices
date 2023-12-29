from uuid import uuid4
from string import ascii_letters, digits
from os.path import exists

REQUEST_ID_ALPHABET = ascii_letters + digits
REQUEST_ID_ALPHABET_LENGTH = len(REQUEST_ID_ALPHABET)


def generate(width: int = 0, fillchar: str = "x") -> str:
    """
    Generate a UUID and make is smaller
    """
    output = ""
    uid = uuid4()
    num = uid.int
    while num:
        num, pos = divmod(num, REQUEST_ID_ALPHABET_LENGTH)
        output += REQUEST_ID_ALPHABET[pos]
    eid = output[::-1]
    if width:
        eid = eid.rjust(width, fillchar)
    return eid


def get_or_create_instance_id(instance_id_path: str = "./instance_id"):
    if exists(instance_id_path):
        with open(instance_id_path, "r", encoding="utf8") as fs:
            return fs.readline().strip()

    instance_id = generate(5)  # 22B
    with open(instance_id_path, "w", encoding="utf8") as fs:
        fs.write(instance_id)
    return instance_id


if __name__ == "__main__":
    sid = generate(16)
    print(sid, len(sid))  # 22B
