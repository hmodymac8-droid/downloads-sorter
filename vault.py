"""A password-protected vault: files moved in are encrypted, and can only be
read again by opening them from the vault or moving them back out.

This is the engine behind the Vault page in sort_gui.pyw. It never touches the
window, so long jobs can run on a background thread.

How it is protected
- The password is stretched with scrypt into a key that unlocks a random
  "vault key". Changing the password re-wraps that key; files stay as they are.
- Every file is encrypted with AES-256-GCM in 1 MB chunks under a random file
  name. The list of files (names, sizes, folders) is encrypted too, so the
  vault folder shows nothing about what is inside.
- Any change to an encrypted file is detected (GCM), so a damaged or tampered
  file is refused instead of opened.
- Opening a file decrypts a copy into a private folder. When the vault locks,
  edits to the copy are saved back into the vault and the copy is removed.
"""

import base64
import json
import os
import secrets
import shutil
import struct
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import sort_downloads as core

VAULT_DIR = core.DATA_DIR / "Vault"
HEADER_FILE = VAULT_DIR / "vault.json"
INDEX_FILE = VAULT_DIR / "index.bin"
# Decrypted copies of opened files: under Local AppData, away from anything the cleaner or sorter scans.
OPEN_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DownloadsSorter" / "VaultOpen"
CHUNK = 1024 * 1024
MAGIC = b"DSV1"
MIN_PASSWORD = 6
SCRYPT = {"n": 2 ** 17, "r": 8, "p": 1}  # about half a second per try, on purpose


class VaultError(Exception):
    """A problem worth showing the user as is."""


class WrongPassword(VaultError):
    pass


class Cancelled(Exception):
    pass


@dataclass
class Item:
    id: str
    name: str
    size: int
    added: float
    folder: str  # where it came from, offered as the default when moving it out


def _aesgcm(key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key)


def _password_key(password: str, salt: bytes, params: dict) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return Scrypt(salt=salt, length=32, n=params["n"], r=params["r"], p=params["p"]).derive(password.encode("utf-8"))


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def exists() -> bool:
    return HEADER_FILE.exists()


def _write_atomic(path: Path, data: bytes) -> None:
    temp = path.with_name(path.name + ".new")
    temp.write_bytes(data)
    os.replace(temp, path)


def _wrap(vault_key: bytes, password: str) -> dict:
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    wrapped = _aesgcm(_password_key(password, salt, SCRYPT)).encrypt(nonce, vault_key, b"vault-key")
    return {"version": 1, "kdf": "scrypt", "params": SCRYPT, "salt": _b64(salt), "nonce": _b64(nonce),
            "key": _b64(wrapped)}


def create(password: str) -> "Vault":
    if exists():
        raise VaultError("A vault already exists.")
    if len(password) < MIN_PASSWORD:
        raise VaultError(f"Use a password of at least {MIN_PASSWORD} characters.")
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    vault_key = secrets.token_bytes(32)
    _write_atomic(HEADER_FILE, json.dumps(_wrap(vault_key, password), indent=1).encode("utf-8"))
    vault = Vault(vault_key, [])
    vault.save_index()
    return vault


def unlock(password: str) -> "Vault":
    from cryptography.exceptions import InvalidTag
    try:
        header = json.loads(HEADER_FILE.read_text(encoding="utf-8"))
        salt, nonce, wrapped = (base64.b64decode(header[k]) for k in ("salt", "nonce", "key"))
    except (OSError, ValueError, KeyError) as error:
        raise VaultError(f"The vault could not be read: {error}")
    try:
        vault_key = _aesgcm(_password_key(password, salt, header["params"])).decrypt(nonce, wrapped, b"vault-key")
    except InvalidTag:
        raise WrongPassword("Wrong password.")
    vault = Vault(vault_key, [])
    vault.load_index()
    return vault


def clear_open_copies() -> list[Path]:
    """Remove decrypted copies left from an earlier session. Returns any still in use."""
    left = []
    if OPEN_DIR.is_dir():
        for folder in OPEN_DIR.iterdir():
            try:
                shutil.rmtree(folder) if folder.is_dir() else folder.unlink()
            except OSError:
                left.append(folder)
    return left


class Vault:
    """An unlocked vault. Forget the object (lock) to drop the key."""

    def __init__(self, key: bytes, items: list[Item]):
        self.key = key
        self.items = items
        self.opened = {}  # item id -> (copy path, mtime and size when opened)

    # --- the encrypted file list ---

    def load_index(self) -> None:
        if not INDEX_FILE.exists():
            self.items = []
            return
        data = INDEX_FILE.read_bytes()
        try:
            plain = _aesgcm(self.key).decrypt(data[:12], data[12:], b"index")
        except Exception:
            raise VaultError("The vault's file list is damaged.")
        self.items = [Item(**item) for item in json.loads(plain)]

    def save_index(self) -> None:
        nonce = secrets.token_bytes(12)
        plain = json.dumps([asdict(item) for item in self.items]).encode("utf-8")
        _write_atomic(INDEX_FILE, nonce + _aesgcm(self.key).encrypt(nonce, plain, b"index"))

    # --- encrypting and decrypting one file, a chunk at a time ---

    def _blob(self, item_id: str) -> Path:
        return VAULT_DIR / f"{item_id}.bin"

    def _encrypt_file(self, source: Path, item_id: str, progress, cancel) -> None:
        cipher, prefix = _aesgcm(self.key), secrets.token_bytes(8)
        size, done = source.stat().st_size, 0
        target = self._blob(item_id).with_suffix(".new")
        try:
            with open(source, "rb") as reader, open(target, "wb") as writer:
                writer.write(MAGIC + prefix)
                index, chunk = 0, reader.read(CHUNK)
                while True:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled
                    following = reader.read(CHUNK) if chunk else b""
                    last = not following
                    # The chunk number and "last" flag are authenticated, so chunks can't be dropped or reordered.
                    aad = item_id.encode() + struct.pack("<I?", index, last)
                    sealed = cipher.encrypt(prefix + struct.pack("<I", index), chunk, aad)
                    writer.write(struct.pack("<I", len(sealed)) + sealed)
                    done += len(chunk)
                    if progress:
                        progress(done, size)
                    if last:
                        break
                    index, chunk = index + 1, following
            os.replace(target, self._blob(item_id))
        except BaseException:
            target.unlink(missing_ok=True)
            raise

    def _chunks(self, item: Item):
        """The decrypted content of a vault file, a chunk at a time. Raises VaultError if it was altered."""
        from cryptography.exceptions import InvalidTag
        cipher = _aesgcm(self.key)
        with open(self._blob(item.id), "rb") as reader:
            header = reader.read(12)
            if header[:4] != MAGIC:
                raise VaultError(f"{item.name} is damaged.")
            prefix, index = header[4:], 0
            while True:
                length = reader.read(4)
                if len(length) < 4:
                    raise VaultError(f"{item.name} is damaged (cut short).")
                sealed = reader.read(struct.unpack("<I", length)[0])
                for last in (False, True):
                    try:
                        chunk = cipher.decrypt(prefix + struct.pack("<I", index), sealed,
                                               item.id.encode() + struct.pack("<I?", index, last))
                        break
                    except InvalidTag:
                        continue
                else:
                    raise VaultError(f"{item.name} is damaged or was changed outside the vault.")
                yield chunk
                if last:
                    return
                index += 1

    def _decrypt_file(self, item: Item, target: Path, progress=None) -> None:
        done = 0
        try:
            with open(target, "wb") as writer:
                for chunk in self._chunks(item):
                    writer.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, item.size)
        except BaseException:
            target.unlink(missing_ok=True)
            raise

    def _matches(self, item: Item, source: Path) -> bool:
        """True if the vault copy decrypts to exactly the source file's bytes."""
        with open(source, "rb") as reader:
            for chunk in self._chunks(item):
                if reader.read(len(chunk)) != chunk:
                    return False
            return reader.read(1) == b""

    # --- what the page does ---

    def add(self, paths: list[Path], progress=None, cancel=None) -> tuple[int, list[str]]:
        """Move files into the vault: encrypt, check, then delete the original for good
        (the Recycle Bin would keep a readable copy)."""
        added, errors = 0, []
        for number, path in enumerate(paths):
            if cancel is not None and cancel.is_set():
                break
            try:
                if not path.is_file():
                    raise VaultError("not a file")
                if core.norm(VAULT_DIR) in core.norm(path) or core.norm(OPEN_DIR) in core.norm(path):
                    raise VaultError("it is already in the vault")
                stat = path.stat()
                item = Item(uuid.uuid4().hex, path.name, stat.st_size, time.time(), str(path.parent))
                report = (lambda done, size, n=number: progress(n, len(paths), path.name, done, size)) \
                    if progress else None
                self._encrypt_file(path, item.id, report, cancel)
                if not self._matches(item, path):
                    self._blob(item.id).unlink(missing_ok=True)
                    raise VaultError("the encrypted copy did not check out, so the file was left where it is")
                self.items.append(item)
                self.save_index()
                added += 1
                try:
                    path.unlink()
                except OSError as error:
                    errors.append(f"{path.name}: copied into the vault, but the original could not be removed "
                                  f"({error.strerror or error})")
            except Cancelled:
                break
            except (OSError, VaultError) as error:
                errors.append(f"{path.name}: {getattr(error, 'strerror', None) or error}")
        return added, errors

    def move_out(self, items: list[Item], folder: Path | None = None, progress=None) -> tuple[int, list[str]]:
        """Decrypt files back to a normal folder (their original one by default) and remove them from the vault."""
        moved, errors = 0, []
        for number, item in enumerate(items):
            try:
                self.close_copy(item)
                destination = folder or Path(item.folder)
                destination.mkdir(parents=True, exist_ok=True)
                target = core.unique_destination(destination, item.name)
                report = (lambda done, size, n=number, i=item: progress(n, len(items), i.name, done, size)) \
                    if progress else None
                self._decrypt_file(item, target, report)
                self.items.remove(item)
                self.save_index()
                self._blob(item.id).unlink(missing_ok=True)
                moved += 1
            except (OSError, VaultError) as error:
                errors.append(f"{item.name}: {getattr(error, 'strerror', None) or error}")
        return moved, errors

    def delete(self, items: list[Item]) -> tuple[int, list[str]]:
        """Remove files from the vault for good."""
        count, errors = 0, []
        for item in items:
            try:
                self.close_copy(item)
                self._blob(item.id).unlink(missing_ok=True)
                self.items.remove(item)
                count += 1
            except OSError as error:
                errors.append(f"{item.name}: {error.strerror or error}")
        self.save_index()
        return count, errors

    def open_copy(self, item: Item) -> Path:
        """Decrypt a working copy into the private folder and return it, ready to open."""
        if item.id in self.opened and self.opened[item.id][0].exists():
            return self.opened[item.id][0]
        folder = OPEN_DIR / secrets.token_hex(8)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / item.name
        self._decrypt_file(item, target)
        stat = target.stat()
        self.opened[item.id] = (target, (stat.st_mtime, stat.st_size))
        return target

    def close_copy(self, item: Item) -> str | None:
        """Save edits made to an opened copy back into the vault, then remove the copy.
        Returns a message if the copy is still in use (it is then kept until next time)."""
        if item.id not in self.opened:
            return None
        copy, before = self.opened[item.id]
        if not copy.exists():
            del self.opened[item.id]
            return None
        stat = copy.stat()
        if (stat.st_mtime, stat.st_size) != before:
            self._encrypt_file(copy, item.id, None, None)  # edits go back in
            item.size = stat.st_size
            self.save_index()
            self.opened[item.id] = (copy, (stat.st_mtime, stat.st_size))
        try:
            shutil.rmtree(copy.parent)
        except OSError:
            return f"{item.name} is still open in another program; close it and lock the vault again."
        del self.opened[item.id]
        return None

    def close_all(self) -> list[str]:
        """Before locking: save and remove every opened copy."""
        problems = []
        for item in [i for i in self.items if i.id in self.opened]:
            try:
                if problem := self.close_copy(item):
                    problems.append(problem)
            except (OSError, VaultError) as error:
                problems.append(f"{item.name}: {error}")
        return problems

    def change_password(self, old: str, new: str) -> None:
        if len(new) < MIN_PASSWORD:
            raise VaultError(f"Use a password of at least {MIN_PASSWORD} characters.")
        unlock(old)  # raises WrongPassword
        _write_atomic(HEADER_FILE, json.dumps(_wrap(self.key, new), indent=1).encode("utf-8"))
