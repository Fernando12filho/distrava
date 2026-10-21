"""AC-01: the API key lives only in the OS keychain, never in argv, SQLite or logs."""

import subprocess

import pytest

from app.coach import keystore
from app.coach.keystore import KeystoreUnavailable, MacKeychain, mask, validate_key

KEY = "sk-ant-api03-Abc_def-123456789"


class FakeSecurity:
    """Stands in for /usr/bin/security; keeps one item like the real keychain."""

    def __init__(self):
        self.calls = []
        self.items = {}

    def __call__(self, argv, input=None, **_kwargs):
        self.calls.append((argv, input))
        if argv[:2] == ["security", "-i"]:
            # add-generic-password -U -s S -a A -w "VALUE"
            parts = input.strip().split(" ")
            service, account = parts[parts.index("-s") + 1], parts[parts.index("-a") + 1]
            self.items[(service, account)] = input.strip().split("-w ", 1)[1].strip('"')
            return subprocess.CompletedProcess(argv, 0, "", "")
        service, account = argv[argv.index("-s") + 1], argv[argv.index("-a") + 1]
        if argv[1] == "find-generic-password":
            if (service, account) not in self.items:
                return subprocess.CompletedProcess(argv, 44, "", "not found")
            return subprocess.CompletedProcess(argv, 0, self.items[(service, account)] + "\n", "")
        if argv[1] == "delete-generic-password":
            found = self.items.pop((service, account), None)
            return subprocess.CompletedProcess(argv, 0 if found else 44, "", "")
        raise AssertionError(argv)


def test_ac_01_saving_reads_back_and_never_puts_the_key_in_argv():
    security = FakeSecurity()
    chain = MacKeychain(run=security)

    chain.set(KEY)

    assert chain.get() == KEY
    for argv, _input in security.calls:
        assert KEY not in " ".join(argv)


def test_missing_key_is_none():
    assert MacKeychain(run=FakeSecurity()).get() is None


def test_delete_removes_the_key_and_tolerates_none_saved():
    security = FakeSecurity()
    chain = MacKeychain(run=security)
    chain.set(KEY)

    chain.delete()
    chain.delete()

    assert chain.get() is None


def test_a_keychain_failure_is_reported_not_swallowed():
    def broken(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 1, "", "user interaction is not allowed")

    with pytest.raises(KeystoreUnavailable):
        MacKeychain(run=broken).get()


def test_a_save_that_does_not_read_back_is_an_error():
    def forgetful(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0 if argv[1] == "-i" else 44, "", "")

    with pytest.raises(KeystoreUnavailable):
        MacKeychain(run=forgetful).set(KEY)


def test_without_a_keychain_saving_refuses_instead_of_falling_back():
    store = keystore.NoKeystore()

    assert store.available is False
    assert store.get() is None
    with pytest.raises(KeystoreUnavailable):
        store.set(KEY)


@pytest.mark.parametrize("raw", ["", "   ", "has space", 'quote"d', "back\\slash", "new\nline", "short", "x" * 301])
def test_ac_01_odd_keys_are_rejected_before_reaching_the_keychain(raw):
    with pytest.raises(ValueError):
        validate_key(raw)


def test_surrounding_whitespace_is_trimmed():
    assert validate_key(f"  {KEY}\n") == KEY


def test_ac_01_only_the_last_four_characters_are_ever_shown():
    assert mask(KEY) == "•••• 6789"
    assert KEY[:-4] not in mask(KEY)
