from typing import cast


class TouchedMeta(type):
    def __new__(cls, name, bases, attrs, **kwargs):
        __touched__ = []
        for attr in attrs:
            attr = cast(str, attr)
            if not attr.startswith("_"):
                __touched__.append(attr)

        gen_class = super().__new__(cls, name, bases, attrs, **kwargs)
        setattr(gen_class, "__touched__", __touched__)  # cls attr
        return gen_class
