class Rejected(Exception):
    pass


class RefreshRequired(Exception):
    pass


class Unavailable(Exception):
    pass


class WsConnectConflict(Exception):
    pass


class SendTooFast(Exception):
    pass
