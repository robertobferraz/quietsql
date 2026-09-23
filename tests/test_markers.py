import pytest
from tests.conftest import marked, pytest_collection_modifyitems, selected


class FakeConfig:
    def __init__(self, markexpr=""):
        self.markexpr = markexpr

    def getoption(self, name, default=None):
        return self.markexpr if name == "markexpr" else default


class FakeItem:
    def __init__(self, *names):
        self.names = set(names)
        self.markers = []

    def get_closest_marker(self, name):
        return pytest.mark.__getattr__(name).mark if name in self.names else None

    def add_marker(self, marker):
        self.markers.append(marker)


def reasons(item):
    return [m.kwargs["reason"] for m in item.markers]


def test_accuracy_is_skipped_when_no_marker_expression_selects_it():
    item = FakeItem("accuracy")
    pytest_collection_modifyitems(FakeConfig(), [item])
    assert reasons(item) == ["accuracy suite runs on demand: pytest -m accuracy"]


def test_accuracy_runs_when_the_marker_expression_mentions_it():
    item = FakeItem("accuracy")
    pytest_collection_modifyitems(FakeConfig("accuracy"), [item])
    assert item.markers == []


def test_slow_runs_by_default():
    item = FakeItem("slow")
    pytest_collection_modifyitems(FakeConfig(), [item])
    assert item.markers == []


def test_network_is_skipped_even_when_accuracy_is_selected():
    item = FakeItem("network")
    pytest_collection_modifyitems(FakeConfig("accuracy"), [item])
    assert reasons(item) == ["network tests run on demand"]


def test_plain_tests_are_never_skipped():
    item = FakeItem()
    pytest_collection_modifyitems(FakeConfig(), [item])
    assert item.markers == []


@pytest.mark.parametrize(
    ("expression", "expected"),
    [("", False), (None, False), ("accuracy", True), ("not accuracy", True)],
)
def test_selected_reads_the_marker_expression(expression, expected):
    assert selected(FakeConfig(expression), "accuracy") is expected


def test_a_directory_named_like_a_marker_does_not_count_as_that_marker():
    item = FakeItem()
    item.keywords = {"accuracy": True}
    assert marked(item, "accuracy") is False
    pytest_collection_modifyitems(FakeConfig(), [item])
    assert item.markers == []
