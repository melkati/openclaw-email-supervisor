"""Credential resolution helpers.

Passwords and tokens are never stored in plaintext inside account JSON
files.  Instead, each sensitive value is a *reference* like:

- ``env:VARIABLE_NAME``  — read from an environment variable.
- ``file:/path/to/file`` — read the first line of a local file.
- ``vault:key_name``     — (future) read from an OS secret store.

The recommended workflow for production is to use ``load_secrets.sh``
which reads files from the ``secrets/`` directory and exports them as
environment variables, then reference them with ``env:VAR_NAME``.

Alternatively, use ``file:`` to read secret files directly without
environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path


class SecretResolutionError(Exception):
    """Raised when a secret reference cannot be resolved."""


def resolve_secret(ref: str) -> str:
    """Resolve a ``password_ref`` / ``token_ref`` string to its value.

    Parameters
    ----------
    ref:
        A reference string in the form ``"scheme:key"``.

        Supported schemes:

        - ``env:VAR_NAME`` — read from environment variable ``VAR_NAME``.
        - ``file:/path``   — read the contents of a local file (trimmed).
        - ``vault:key``    — (future) OS keyring / secret manager.

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
            "Expected 'scheme:key' (e.g. 'env:MY_PASS' or 'file:secrets/password')."
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

    if scheme == "file":
        path = Path(key.strip()).expanduser()
        if not path.is_file():
            raise SecretResolutionError(
                f"Secret file not found: {path}"
            )
        value = path.read_text(encoding="utf-8").strip()
        if not value:
            raise SecretResolutionError(
                f"Secret file is empty: {path}"
            )
        return value

    if scheme == "vault":
        # Future: integrate with OS keyring / secret manager
        raise SecretResolutionError(
            f"Vault backend is not implemented yet (key={key!r})."
        )

    raise SecretResolutionError(f"Unknown secret scheme: {scheme!r}.")
