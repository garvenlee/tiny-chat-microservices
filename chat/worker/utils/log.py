import logging
from uvicorn.logging import DefaultFormatter


def set_default_logger(name: str):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = DefaultFormatter(
        "[%(asctime)s] %(levelprefix)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        use_colors=True,
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
