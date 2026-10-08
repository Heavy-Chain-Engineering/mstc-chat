import backend


def test_backend_package_imports() -> None:
    assert backend.__doc__ == "MSTC Chat server."
