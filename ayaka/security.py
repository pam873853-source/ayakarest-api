"""Cryptographic primitives: Argon2id passwords, peppered API key hashes, tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import re
import secrets
import string

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)  # Argon2id
_ALPHABET = string.ascii_letters + string.digits
API_KEY_PREFIX = "ayaka_live_"
API_KEY_SECRET_LEN = 40  # 40 base62 chars ≈ 238 bits of entropy
API_KEY_RE = re.compile(r"^ayaka_live_[A-Za-z0-9]{40}$")

# Dummy hash so login timing is similar for unknown emails.
_DUMMY_HASH = _ph.hash(secrets.token_hex(16))


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _ph.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


PASSWORD_RULES = "Minimal 8 karakter, mengandung huruf besar, huruf kecil, dan angka."


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 8:
        problems.append("Password minimal 8 karakter")
    if len(password) > 128:
        problems.append("Password maksimal 128 karakter")
    if not re.search(r"[a-z]", password):
        problems.append("Password harus mengandung huruf kecil")
    if not re.search(r"[A-Z]", password):
        problems.append("Password harus mengandung huruf besar")
    if not re.search(r"\d", password):
        problems.append("Password harus mengandung angka")
    return problems


def generate_api_key() -> str:
    """`ayaka_live_<40 base62 chars>` using the OS CSPRNG (secrets)."""
    return API_KEY_PREFIX + "".join(secrets.choice(_ALPHABET) for _ in range(API_KEY_SECRET_LEN))


def hash_api_key(raw_key: str) -> str:
    """HMAC-SHA256 with a server-side pepper — a DB leak alone cannot verify keys."""
    pepper = get_settings().api_key_pepper.encode()
    return hmac.new(pepper, raw_key.encode(), hashlib.sha256).hexdigest()


def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hmac_hex(key: str, value: str) -> str:
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest((a or "").encode(), (b or "").encode())


def mask_ip(ip: str | None) -> str | None:
    """IPv4 → /24, IPv6 → /48. Never store full addresses."""
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return None
    if addr.version == 4:
        return str(ipaddress.ip_network(f"{addr}/24", strict=False).network_address) + "/24"
    return str(ipaddress.ip_network(f"{addr}/48", strict=False).network_address) + "/48"


def _fernet() -> Fernet:
    digest = hashlib.sha256(("fernet:" + get_settings().secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
