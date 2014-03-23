class APIException(Exception):
    pass 

class InvalidNonce(Exception):
    pass

class NonceLimitReached(InvalidNonce):
    pass

class CryptsyException(APIException):
    pass

