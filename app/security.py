"""Пароли, подписанные куки сессий и защита от перебора паролей.

Пароли — scrypt из стандартной библиотеки (без внешних зависимостей).
Сессия — подписанная кука (itsdangerous): {"k": вид, "id": номер}. Подделать
её без SECRET_KEY нельзя; выход из аккаунта — просто удаление куки.
"""

import hashlib
import hmac
import os
import time
from collections import defaultdict, deque

from itsdangerous import BadSignature, URLSafeTimedSerializer

from .config import settings

CUSTOMER_COOKIE = "briz_user"
STAFF_COOKIE = "briz_staff"
CUSTOMER_DAYS = 180  # гость входит редко — держим долго
STAFF_DAYS = 14

_N, _R, _P = 2**14, 8, 1  # ~16 МБ памяти на проверку: медленно для перебора, быстро для входа


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt, dk = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    test = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=_N, r=_R, p=_P, dklen=32)
    return hmac.compare_digest(test.hex(), dk)


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="briz-session")


def make_session(kind: str, ident: int) -> str:
    return _serializer().dumps({"k": kind, "id": ident})


def read_session(value: str | None, kind: str, days: int) -> int | None:
    if not value:
        return None
    try:
        data = _serializer().loads(value, max_age=days * 86400)
    except BadSignature:
        return None
    if not isinstance(data, dict) or data.get("k") != kind or not isinstance(data.get("id"), int):
        return None
    return data["id"]


class Throttle:
    """Не больше `limit` неудачных входов за `window` секунд на ключ (телефон, логин).

    В памяти процесса: сервер один, после перезапуска счётчик обнуляется — для
    кафе этого достаточно."""

    def __init__(self, limit: int = 5, window: int = 15 * 60):
        self.limit, self.window = limit, window
        self.fails: dict[str, deque] = defaultdict(deque)

    def _clean(self, key: str) -> deque:
        q = self.fails[key]
        while q and q[0] < time.monotonic() - self.window:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        return len(self._clean(key)) >= self.limit

    def fail(self, key: str) -> None:
        self._clean(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self.fails.pop(key, None)


login_throttle = Throttle()
