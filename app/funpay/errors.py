class FunPayError(Exception):
    """Base error for FunPay client failures."""


class UnauthorizedError(FunPayError):
    """The golden_key is invalid or the session has expired."""


class RequestError(FunPayError):
    """FunPay returned an unexpected status code or payload."""


class MessageNotSentError(FunPayError):
    """FunPay rejected a chat message."""


class LotSaveError(FunPayError):
    """FunPay rejected a lot update."""
