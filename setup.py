"""Minimal setup.py for editable installs and packaging."""

from setuptools import setup, find_packages

setup(
    name="openclaw-email-supervisor",
    version="0.1.0",
    description="Multi-account IMAP email supervisor — OpenClaw skill",
    author="melkati",
    url="https://github.com/melkati/openclaw-email-supervisor",
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.11",
    install_requires=[
        "aioimaplib>=1.1.0",
        "aiohttp>=3.9.0",
        "python-telegram-bot>=21.0",
        "cryptography>=42.0",
        "python-dateutil>=2.9",
        "croniter>=2.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0",
            "pytest-asyncio>=0.23",
        ],
    },
    entry_points={
        "console_scripts": [
            "email-supervisor=email_supervisor.main:cli_main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
    ],
)
