"""Compatibility shim for editable installs with older pip versions."""

from setuptools import find_packages, setup


setup(
    name="pysoroban-compiler",
    version="0.1.0",
    description="A deterministic, statically typed Python contract compiler for Stellar",
    packages=find_packages("src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
    entry_points={"console_scripts": ["pysoroban=pysoroban.cli:main"]},
)
