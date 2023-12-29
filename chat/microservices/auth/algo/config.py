from attrs import define
from typing import Optional, Callable


@define(slots=True)
class Configuraton:
    ACCESS_TOKEN_NAME: str = "access_token"
    REFRESH_TOKEN_NAME: str = "refresh_token"

    AUTHORIZATION_HEADER: str = "authorization"
    AUTHORIZATION_HEADER_PREFIX: str = "Bearer"
    AUTHORIZATION_HEADER_REFRESH_PREFIX: str = "Refresh"

    EXPIRATION_DELTA: int = 864000
    LEEWAY: int = 60 * 3

    SECRET_KEY: str = "You never know this"
    USER_ID: str = "uid"

    verify_exp: bool = True

    algorithm: str = "HS256"
    user_secret_enabled: bool = False  # scratch secret from user table
    generate_private_key: Optional[Callable] = None

    # custom
    generate_access_token: Optional[Callable] = None
    generate_refresh_token: Optional[Callable] = None
    store_refresh_token: Optional[Callable] = None
    retrieve_refresh_token: Optional[Callable] = None

    debug: bool = False
