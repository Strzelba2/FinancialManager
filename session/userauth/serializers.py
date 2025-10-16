
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from rest_framework import serializers
from typing import Any, Dict
import logging

logger = logging.getLogger("session-auth")

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    """
    Serializer for authenticating users via email and password.

    Fields:
        - email (str): Required. The user's email.
        - password (str): Required. The user's password (write-only).
    """
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Authenticate the user using email and password.

        Raises:
            ValidationError: If authentication fails or user is inactive.

        Returns:
            dict: {'user': User instance}
        """
        user = authenticate(username=attrs['email'], password=attrs['password'])

        if not user:
            logger.warning("Authentication failed for email.")
            raise serializers.ValidationError({'error': 'Incorrect email or password.'})

        if not user.is_active:
            logger.warning("Inactive user attempted login.")
            raise serializers.ValidationError({'error': 'User is disabled.'})

        logger.info("User authenticated successfully.")
        return {'user': user}


class RegisterSerializer(serializers.ModelSerializer):
    """
    Serializer for registering a new user.

    Fields:
        - first_name
        - last_name
        - username
        - email
        - password (write-only)
    """
    password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'password']

    def create(self, validated_data: Dict[str, Any]) -> User:
        """
        Create a new user instance with hashed password.

        Args:
            validated_data (dict): Validated data from registration form.

        Returns:
            User: The created User object.
        """
        username = validated_data.pop('username')
        email = validated_data.pop('email')
        password = validated_data.pop('password')
        logger.info("Registering new user.")
        
        return User.objects.create_user(username=username, email=email, password=password, **validated_data)


class Cryptodata(serializers.Serializer):
    """
    Represents a single cryptographic operation.

    Depending on the value of `kind`, different fields are required:

    - "encrypt": requires `plaintext_b64`, returns `ciphertext_b64` and `nonce_b64`
    - "decrypt": requires `ciphertext_b64` and `nonce_b64`, returns `plaintext_b64`
    - "hmac": requires `plaintext_b64`, returns a MAC value
    """
    id = serializers.CharField()
    kind = serializers.ChoiceField(choices=["encrypt", "decrypt", "hmac"])
    plaintext_b64 = serializers.CharField(required=False)
    nonce_b64 = serializers.CharField(required=False)
    ciphertext_b64 = serializers.CharField(required=False)


class CryptoBatchRequest(serializers.Serializer):
    """
    A batch of cryptographic operations associated with a user.

    Useful for performing multiple crypto tasks (e.g. encrypt/decrypt/hmac) in a single API call.
    """
    username = serializers.CharField()
    data = Cryptodata(many=True)
