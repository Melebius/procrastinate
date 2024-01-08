import psycopg
import pytest

from procrastinate import exceptions, psycopg_connector, sync_psycopg_connector


@pytest.fixture
def connector():
    return psycopg_connector.PsycopgConnector()


async def test_wrap_exceptions_wraps():
    @psycopg_connector.wrap_exceptions
    async def corofunc():
        raise psycopg.DatabaseError

    coro = corofunc()

    with pytest.raises(exceptions.ConnectorException):
        await coro


async def test_wrap_exceptions_success():
    @psycopg_connector.wrap_exceptions
    async def corofunc(a, b):
        return a, b

    assert await corofunc(1, 2) == (1, 2)


@pytest.mark.parametrize(
    "method_name",
    [
        "_create_pool",
        "close_async",
        "execute_query_async",
        "execute_query_one_async",
        "execute_query_all_async",
        "listen_notify",
    ],
)
def test_wrap_exceptions_applied(method_name, connector):
    assert getattr(connector, method_name)._exceptions_wrapped is True


async def test_open_async_no_pool_specified(mocker, connector):
    mocker.patch.object(connector, "_create_pool", return_value=mocker.AsyncMock())

    await connector.open_async()

    assert connector._create_pool.call_count == 1
    assert connector._async_pool.open.await_count == 1


async def test_open_async_pool_argument_specified(mocker, connector):
    mocker.patch.object(connector, "_create_pool")
    pool = mocker.AsyncMock()

    await connector.open_async(pool)

    assert connector._pool_externally_set is True
    assert connector._create_pool.call_count == 0
    assert connector._async_pool == pool


def test_get_pool(connector):
    with pytest.raises(exceptions.AppNotOpen):
        _ = connector.pool


async def test_get_sync_connector__open(connector):
    await connector.open_async()
    assert connector.get_sync_connector() is connector
    await connector.close_async()


async def test_get_sync_connector__not_open(connector):
    sync = connector.get_sync_connector()
    assert isinstance(sync, sync_psycopg_connector.SyncPsycopgConnector)
    assert connector.get_sync_connector() is sync
    assert sync._pool_args == connector._pool_args
