from cryptography.fernet import Fernet, InvalidToken


class PasswordCipher:
    """Symmetric encryption for account passwords.

    Hashing is not an option here: the plaintext must be delivered to buyers.
    """

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()

    def is_encrypted(self, value: str) -> bool:
        try:
            self._fernet.decrypt(value.encode())
        except InvalidToken:
            return False
        return True
