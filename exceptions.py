class BaseError(Exception):
    """
    Base for all Orchestra API Errors.
    """
    pass


class PermissionDenied(BaseError):
    """
    Exception for no permission.
    """
    pass


class RequestFailed(BaseError):
    """
    Exception when sucess attribute in response payload is not True.
    """
    pass


class UnknownError(BaseError):
    """
    Exception for the reasons we don't know.
    """
    pass