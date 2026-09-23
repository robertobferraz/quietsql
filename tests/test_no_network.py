import socket
from contextlib import contextmanager

import pytest
import pytest_socket

from quietsql.config import Config
from quietsql.ui.fake_services import build_fake_services
from quietsql.wiring import build_services


def assert_sockets_are_blocked():
    with pytest.raises(pytest_socket.SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


@contextmanager
def recorded_socket_attempts():
    guarded = socket.socket
    attempts = []

    def record(*args, **kwargs):
        attempts.append(args)
        return guarded(*args, **kwargs)

    socket.socket = record
    try:
        yield attempts
    finally:
        socket.socket = guarded


def test_building_real_services_opens_no_socket(tmp_path):
    pytest_socket.disable_socket()
    assert_sockets_are_blocked()
    cfg = Config(cache_dir=tmp_path / "cache", config_dir=tmp_path / "cfg")
    with recorded_socket_attempts() as attempts:
        services = build_services(cfg)
        assert services.model_status.ready() is False
    assert attempts == []


def test_fake_flow_opens_no_socket():
    pytest_socket.disable_socket()
    assert_sockets_are_blocked()
    services = build_fake_services(token_delay=0.0)
    source = services.sources.list()[0]
    with recorded_socket_attempts() as attempts:
        assert services.ask(source.id, "vendas por cidade").status.value == "ok"
    assert attempts == []


@pytest.mark.slow
def test_real_portuguese_question_flow_opens_no_socket(tmp_path):
    pytest_socket.disable_socket()
    assert_sockets_are_blocked()
    import duckdb

    db = tmp_path / "t.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE sales AS SELECT i AS id, i * 2.0 AS amount FROM range(100) t(i)")
    con.close()
    services = build_services(Config())
    if not services.model_status.ready():
        pytest.skip("models not downloaded")
    source = services.sources.open_file(str(db))
    with recorded_socket_attempts() as attempts:
        answer = services.ask(source.id, "qual o valor total das vendas")
    assert attempts == []
    assert answer.sql.text
    assert answer.timings.translate_ms > 0
