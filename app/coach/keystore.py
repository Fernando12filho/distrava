"""Where the AI provider's API key lives: the OS keychain, nowhere else (AC-01).

macOS only for now, through the built-in `security` tool, so the app needs no
new dependency. When Distrava is shared, a `keyring`-backed class with the same
get/set/delete replaces MacKeychain here and nothing else changes. Without a
keychain the key is refused, never saved to a file or SQLite instead.
"""

import shutil
import subprocess
import sys

SERVICE = "Distrava"
ACCOUNT = "anthropic-api-key"
_NOT_FOUND = 44  # `security` exit code for a missing item

MIN_KEY_LENGTH = 20
MAX_KEY_LENGTH = 300


class KeystoreUnavailable(Exception):
    pass


def validate_key(raw):
    key = (raw or "").strip()
    if not MIN_KEY_LENGTH <= len(key) <= MAX_KEY_LENGTH:
        raise ValueError(f"an API key is {MIN_KEY_LENGTH}–{MAX_KEY_LENGTH} characters")
    # The key reaches `security` inside a quoted command line, so anything
    # that could break the quoting is refused rather than escaped.
    if any(c.isspace() or c in "\"'\\" or not c.isprintable() for c in key):
        raise ValueError("an API key has no spaces, quotes or backslashes")
    return key


def mask(key):
    return f"•••• {key[-4:]}"


class MacKeychain:
    available = True

    def __init__(self, run=subprocess.run):
        self._run = run

    def get(self):
        result = self._run(
            ["security", "find-generic-password", "-s", SERVICE, "-a", ACCOUNT, "-w"],
            capture_output=True,
            text=True,
        )
        if result.returncode == _NOT_FOUND:
            return None
        if result.returncode != 0:
            raise KeystoreUnavailable("the keychain could not be read")
        return result.stdout.strip() or None

    def set(self, key):
        key = validate_key(key)
        # Through stdin (`security -i`), not argv: arguments are visible to
        # every process on the machine via `ps`.
        self._run(
            ["security", "-i"],
            input=f'add-generic-password -U -s {SERVICE} -a {ACCOUNT} -w "{key}"\n',
            capture_output=True,
            text=True,
        )
        # `security -i` exits 0 even when a command inside it fails.
        if self.get() != key:
            raise KeystoreUnavailable("the keychain did not keep the key")

    def delete(self):
        result = self._run(
            ["security", "delete-generic-password", "-s", SERVICE, "-a", ACCOUNT],
            capture_output=True,
            text=True,
        )
        if result.returncode not in (0, _NOT_FOUND):
            raise KeystoreUnavailable("the keychain could not be changed")


class MemoryKeystore:
    """For tests: behaves like a keychain, forgets everything on exit."""

    available = True

    def __init__(self):
        self._key = None

    def get(self):
        return self._key

    def set(self, key):
        self._key = validate_key(key)

    def delete(self):
        self._key = None


class NoKeystore:
    available = False

    def get(self):
        return None

    def set(self, key):
        raise KeystoreUnavailable("this computer has no keychain Distrava can use")

    def delete(self):
        pass


def default_keystore():
    if sys.platform == "darwin" and shutil.which("security"):
        return MacKeychain()
    return NoKeystore()
