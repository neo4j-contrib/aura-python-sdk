import re

import aura_python_sdk


def test_version_is_exported() -> None:
    # Builds between tags carry a local suffix, e.g. 0.1.1.dev3+g8d7381f.
    assert re.fullmatch(
        r"\d+\.\d+\.\d+(\.dev\d+|a\d+|b\d+|rc\d+)?(\+[\w.]+)?", aura_python_sdk.__version__
    )


def test_package_is_typed() -> None:
    from importlib.resources import files

    assert files("aura_python_sdk").joinpath("py.typed").is_file()
