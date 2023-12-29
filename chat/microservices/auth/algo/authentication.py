import os
import jwt
import binascii

import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from .config import Configuraton


HANDLER_CUSTOM_METHODS = [
    "store_refresh_token",
    "retrieve_refresh_token",
]


logger = logging.getLogger("AuthHandler")

class AuthHandler:
    config: Configuraton

    def __init__(self, config: Configuraton) -> None:
        self.config = config
        self.load_from_config(config)    
        
    def load_from_config(self, config:Configuraton):
        unimplemented = []
        for name in HANDLER_CUSTOM_METHODS:
            func = getattr(config, name)
            if func and callable(func):
                setattr(self, name, func)
            else:
                unimplemented.append(name)
        
        if unimplemented:
            raise Exception(f"You must convey customize handler implementaion: {unimplemented}")

    def _get_payload(self, uid: int) -> dict:
        payload = {self.config.USER_ID: uid}
        delta = timedelta(seconds=self.config.EXPIRATION_DELTA)
        exp = datetime.utcnow() + delta
        payload["exp"] = exp
        return payload

    def generate_access_token(self, uid: int) -> str:
        payload = self._get_payload(uid)
        secret = self.config.SECRET_KEY
        algorithm = self.config.algorithm
        access_token = jwt.encode(payload, secret, algorithm=algorithm)
        return access_token

    def generate_refresh_token(self, n: int = 24):
        return str(binascii.hexlify(os.urandom(n)), "utf-8")

    def is_payload_valid(self, payload):
        return self.config.USER_ID in payload and "exp" in payload

    def _decode(self, token: str, verify: bool = True) -> Dict[str, Any]:

        secret = self.config.SECRET_KEY
        algorithm = self.config.algorithm

        decoded = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            verify=verify,
            options={"verify_exp": self.config.verify_exp},
        )
        return decoded
