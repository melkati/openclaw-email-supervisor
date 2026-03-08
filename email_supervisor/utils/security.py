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
import logging


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
    logging.debug(f"Resolving secret reference: {ref}")
    if not ref.strip():
        raise SecretResolutionError(
            "Secret reference is empty. Ensure all references are properly defined."
        )

    if ref is None:
        raise SecretResolutionError("Secret reference is None. Ensure all references are properly defined.")

    if ":" not in ref:
        raise SecretResolutionError(
            f"Invalid secret reference format: '{ref}'. "
            "Expected 'scheme:key' (e.g. 'env:MY_PASS' or 'file:secrets/password')."
        )

    scheme, key = ref.split(":", 1)

    if scheme == "env":
        value = os.getenv(key)
        logging.debug(f"Resolved env secret '{key}': {value}")
        if not value:
            raise SecretResolutionError(f"Environment variable '{key}' is not set.")
        return value

    elif scheme == "file":
        try:
            with open(key, "r") as f:
                value = f.read().strip()
                logging.debug(f"Resolved file secret '{key}': {value}")
                return value
        except FileNotFoundError:
            raise SecretResolutionError(f"Secret file '{key}' not found.")
        except Exception as e:
            raise SecretResolutionError(f"Error reading secret file '{key}': {e}")

    else:
        raise SecretResolutionError(f"Unsupported secret scheme: '{scheme}'.")
