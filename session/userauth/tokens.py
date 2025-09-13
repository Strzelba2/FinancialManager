from django.contrib.auth.tokens import PasswordResetTokenGenerator


class AccountActivationTokenGenerator(PasswordResetTokenGenerator):
    """
    Token generator for account activation.

    Extends Django's `PasswordResetTokenGenerator` to create a unique
    token based on the user’s primary key, the timestamp, and whether
    the account is active.

    This ensures that the activation token becomes invalid once the user
    is activated, preventing reuse of old tokens.
    """
    def _make_hash_value(self, user, timestamp):
        """
        Generate a unique hash value for the user.

        Args:
            user (AbstractBaseUser): The user instance for which to generate the token.
            timestamp (int): The timestamp of the token generation.

        Returns:
            str: A string representing the unique value to be hashed.
        """
        return f"{user.pk}{timestamp}{user.is_active}"


account_activation_token = AccountActivationTokenGenerator()
