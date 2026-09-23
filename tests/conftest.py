import inspect

import pytest

pytest_plugins = ["nicegui.testing.user_plugin"]


def selected(config, marker):
    return marker in (config.getoption("markexpr", default="") or "")


def marked(item, marker):
    return item.get_closest_marker(marker) is not None


def pytest_collection_modifyitems(config, items):
    for item in items:
        if marked(item, "network"):
            item.add_marker(pytest.mark.skip(reason="network tests run on demand"))
        if marked(item, "accuracy") and not selected(config, "accuracy"):
            item.add_marker(
                pytest.mark.skip(reason="accuracy suite runs on demand: pytest -m accuracy")
            )


def _members(protocol):
    return sorted(
        name
        for name, value in vars(protocol).items()
        if callable(value) and not name.startswith("_")
    )


def _public_signature(func):
    parameters = list(inspect.signature(func).parameters.values())[1:]
    return [(p.name, p.kind, p.default) for p in parameters]


@pytest.fixture
def conforms_to_port():
    def check(adapter, protocol):
        expected = _members(protocol)
        assert expected
        for name in expected:
            implementation = getattr(adapter, name, None)
            assert callable(implementation), f"{adapter.__name__} is missing {name}"
            assert _public_signature(implementation) == _public_signature(getattr(protocol, name))

    return check
