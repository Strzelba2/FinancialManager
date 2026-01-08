class ImportMismatchError(Exception):
    """Raised when provided amount_after disagrees with computed balance."""
    def __init__(self, message="balance is not correct"):
        super().__init__(message)
      
        
class DuplicateTransactionError(Exception):
    """ Raised when a transaction is detected as a duplicate (same key characteristics)."""
    def __init__(self, message="Transactions is duplicate"):
        super().__init__(message)
   
        
class UnknownAccountError(Exception):
    """Raised when an account does not exist or does not belong to the given user."""
    def __init__(self, message="Unknown account error"):
        super().__init__(message)
  
        
class UnknownUserError(Exception):
    """Raised when a user does not exist (or is not authorized for the operation)."""
    def __init__(self, message="Unknown User Error"):
        super().__init__(message)
        