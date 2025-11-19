#!/usr/bin/env python3
"""Setup script for Supatask CLI."""

from setuptools import setup

setup(
    name="supatask",
    version="1.0.0",
    description="A Redis-based task manager CLI",
    author="Supatask",
    py_modules=["supatask_cli"],
    install_requires=[
        "httpx>=0.26.0",
        "typer>=0.9.0",
        "rich>=13.7.0",
        "python-dateutil>=2.8.2",
    ],
    entry_points={
        "console_scripts": [
            "supatask=supatask_cli:app",
        ],
    },
    python_requires=">=3.11",
)
