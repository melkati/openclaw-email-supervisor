"""Credential resolution helpers.

Passwords and tokens are never stored in plaintext inside account JSON
files.  Instead, each sensitive value is a *reference* like:

- ``env:VARIABLE_NAME`` — read from an environment variable.
- ``vault:key_name``    — (future) read from an OS secret store.

This module resolves those references at runtime.
"""

from __future__ import annotations

import os


class SecretResolutionError(Exception):
    """Raised when a secret reference cannot be resolved."""


def resolve_secret(ref: str) -> str:
    """Resolve a ``password_ref`` / ``token_ref`` string to its value.

    Parameters
    ----------
    ref:
        A reference string in the form ``"scheme:key"``.

    Returns
    -------
    str
        The resolved secret value.

    Raises
    ------
    SecretResolutionError
        If the scheme is unknown or the key cannot be found.
    """
    if not ref or ":" not in ref:
        raise SecretResolutionError(
            f"Invalid secret reference format: {ref!r}. "
            "Expected 'scheme:key' (e.g. 'env:MY_PASS')."
        )

    scheme, key = ref.split(":", 1)
    scheme = scheme.strip().lower()

    if scheme == "env":
        value = os.environ.get(key.strip())
        if value is None:
            raise SecretResolutionError(
                f"Environment variable {key!r} is not set."
            )
        return value

    if scheme == "vault":
        # Future: integrate with OS keyring / secret manager
        raise SecretResolutionError(
            f"Vault backend is not implemented yet (key={key!r})."
        )

    raise SecretResolutionError(f"Unknown secret scheme: {scheme!r}.")
