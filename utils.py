# pylint: skip-file
from passlib.context import CryptContext

# Настраиваем контекст для хэширования
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

#Функция для хэширования пароля.
def hash_password(password: str) -> str:
    """
    Функция для хэширования пароля.
    """
    return pwd_context.hash(password)

#Функция для проверки пароля.
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Функция для проверки пароля.
    """
    return pwd_context.verify(plain_password, hashed_password)
