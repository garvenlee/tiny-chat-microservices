# copy from sanic_httpauth
import hmac

_builtin_safe_str_cmp = getattr(hmac, "compare_digest", None)


def safe_str_cmp(a, b):
    """This function compares strings in somewhat constant time.  This
    requires that the length of at least one string is known in advance.
    Returns `True` if the two strings are equal, or `False` if they are not.
    .. versionadded:: 0.7
    """
    if isinstance(a, str):
        a = a.encode("utf-8")
    if isinstance(b, str):
        b = b.encode("utf-8")

    if _builtin_safe_str_cmp is not None:
        return _builtin_safe_str_cmp(a, b)

    if len(a) != len(b):
        return False

    rv = 0
    for x, y in zip(a, b):
        rv |= x ^ y

    return rv == 0
