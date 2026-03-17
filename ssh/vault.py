"""
Credential Vault
================
AES-256-GCM encryption for SSH passwords.
SSH keys are stored as file paths (never contents) — the key file
itself lives on the CellClaw host filesystem.

Storage: vault.json in the CellClaw data directory.
Master key: derived from a server-side secret via PBKDF2.
"""

from __future__ import annotations
import os
import json
import base64
import hashlib
import secrets
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_VAULT_FILE = Path(__file__).parent.parent / "data" / "vault.json"
_MASTER_KEY_ENV = "OMICSCLAW_VAULT_KEY"


def _get_master_key() -> bytes:
    """
    Derive a 32-byte AES key from the server-side master secret.
    Set OMICSCLAW_VAULT_KEY env var, or a random one is auto-generated
    and stored in data/.vault_key (suitable for single-node deployments).
    """
    raw = os.environ.get(_MASTER_KEY_ENV)
    if raw:
        return hashlib.sha256(raw.encode()).digest()

    # Fallback: auto-generated key stored on disk
    key_file = Path(__file__).parent.parent / "data" / ".vault_key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key_file.exists():
        return base64.b64decode(key_file.read_text().strip())
    else:
        key = secrets.token_bytes(32)
        key_file.write_text(base64.b64encode(key).decode())
        key_file.chmod(0o600)
        return key


def encrypt_password(plaintext: str) -> str:
    """
    Encrypt a password string.
    Returns a base64-encoded token: nonce(12) + ciphertext.
    """
    key = _get_master_key()
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    token = base64.b64encode(nonce + ct).decode()
    return token


def decrypt_password(token: str) -> str:
    """Decrypt a vault token back to plaintext."""
    key = _get_master_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(token)
    nonce, ct = raw[:12], raw[12:]
    return aesgcm.decrypt(nonce, ct, None).decode()


class CredentialVault:
    """
    Persists encrypted credentials to vault.json.
    Key format: "{discord_user_id}:{server_id}"
    """

    def __init__(self, vault_path: Path = _VAULT_FILE):
        self._path = vault_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text())
            except Exception:
                return {}
        return {}

    def _save(self):
        self._path.write_text(json.dumps(self._data, indent=2))
        self._path.chmod(0o600)

    def store_password(self, discord_user_id: str, server_id: str, password: str) -> str:
        """
        Encrypt and store a password.
        Returns the vault token (store this in ServerConfig.password_token).
        """
        token = encrypt_password(password)
        key = f"{discord_user_id}:{server_id}"
        self._data[key] = token
        self._save()
        return token

    def retrieve_password(self, discord_user_id: str, server_id: str) -> Optional[str]:
        """Retrieve and decrypt a stored password. Returns None if not found."""
        key = f"{discord_user_id}:{server_id}"
        token = self._data.get(key)
        if not token:
            return None
        try:
            return decrypt_password(token)
        except Exception:
            return None

    def delete(self, discord_user_id: str, server_id: str):
        """Remove a stored credential."""
        key = f"{discord_user_id}:{server_id}"
        self._data.pop(key, None)
        self._save()

    def has(self, discord_user_id: str, server_id: str) -> bool:
        return f"{discord_user_id}:{server_id}" in self._data
