import datetime
import json
import logging

import configargparse as argparse
import pytest

from procrastinate import app, cli, connector, exceptions, worker
from procrastinate.connector import BaseConnector


@pytest.mark.parametrize(
    "verbosity, log_level", [(0, "INFO"), (1, "DEBUG"), (2, "DEBUG")]
)
def test_get_log_level(verbosity, log_level):
    assert cli.get_log_level(verbosity=verbosity) == getattr(logging, log_level)


def test_configure_logging(mocker, caplog):
    config = mocker.patch("logging.basicConfig")

    caplog.set_level("DEBUG")

    cli.configure_logging(verbosity=1, format="{message}, yay!", style="{")

    config.assert_called_once_with(
        level=logging.DEBUG, format="{message}, yay!", style="{"
    )
    records = [record for record in caplog.records if record.action == "set_log_level"]
    assert len(records) == 1
    assert records[0].value == "DEBUG"


def test_main(mocker):
    mock = mocker.patch("procrastinate.cli.cli", new=mocker.AsyncMock())
    cli.main()
    mock.assert_called_once()


@pytest.mark.parametrize(
    "input, output",
    [
        (["worker", "-q", "a,b"], {"command": "worker", "queues": ["a", "b"]}),
        (["worker", "-q", ""], {"command": "worker", "queues": None}),
        (["worker", "--wait"], {"command": "worker", "wait": True}),
        (["worker", "--one-shot"], {"command": "worker", "wait": False}),
        (
            ["worker", "--no-listen-notify"],
            {"command": "worker", "listen_notify": False},
        ),
        (
            ["worker", "--delete-jobs", "never"],
            {"command": "worker", "delete_jobs": worker.DeleteJobCondition.NEVER},
        ),
        (["defer", "x"], {"command": "defer", "task": "x"}),
        (["defer", "x", "{}"], {"command": "defer", "task": "x", "json_args": "{}"}),
        (
            ["defer", "x", "--at", "2023-01-01T00:00:00"],
            {
                "command": "defer",
                "at": datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc),
            },
        ),
        (
            ["defer", "x", "--in", "3600"],
            {
                "command": "defer",
                "in_": {"seconds": 3600},
            },
        ),
        (
            ["schema"],
            {
                "command": "schema",
                "action": None,
            },
        ),
        (
            ["schema", "--apply"],
            {
                "command": "schema",
                "action": "apply",
            },
        ),
        (
            ["schema", "--read"],
            {
                "command": "schema",
                "action": "read",
            },
        ),
        (
            ["schema", "--migrations-path"],
            {
                "command": "schema",
                "action": "migrations_path",
            },
        ),
    ],
)
def test_parser(input, output):
    result = vars(cli.get_parser().parse_args(input))

    print(result)
    for key, value in output.items():
        assert result[key] == value


@pytest.mark.parametrize(
    "input, error",
    [
        ([], "the following arguments are required: command"),
        (["-a", "foobar"], "Could not load app from foobar"),
        (["defer", "--at", "foo"], "invalid parse_datetime value: 'foo'"),
        (
            ["defer", "--at", "2023-01-01", "--in", "12"],
            "argument --in: not allowed with argument --at",
        ),
    ],
)
def test_parser__error(input, error, capsys):
    with pytest.raises(SystemExit):
        cli.get_parser().parse_args(input)

    assert error in capsys.readouterr().err


@pytest.mark.parametrize(
    "input, output", [(None, {}), ("{}", {}), ("""{"a": "b"}""", {"a": "b"})]
)
def test_load_json_args(input, output):
    assert cli.load_json_args(input, json.loads) == output


@pytest.mark.parametrize("input", ["", "{", "[1, 2, 3]", '"yay"'])
def test_load_json_args_error(input):
    with pytest.raises(ValueError):
        assert cli.load_json_args(input, json.loads)


def test_configure_task_known(app):
    @app.task(name="foobar", queue="marsupilami")
    def mytask():
        pass

    job = cli.configure_task(app, "foobar", {}, allow_unknown=False).job
    assert job.task_name == "foobar"
    assert job.queue == "marsupilami"


def test_configure_task_unknown(app):
    job = cli.configure_task(app, "foobar", {}, allow_unknown=True).job
    assert job.task_name == "foobar"
    assert job.queue == "default"


def test_test_configure_task_error(app):
    with pytest.raises(exceptions.TaskNotFound):
        assert cli.configure_task(app, "foobar", {}, allow_unknown=False)


@pytest.mark.parametrize(
    "method_name",
    [
        "execute_query",
        "execute_query_one",
        "execute_query_all",
        "execute_query_async",
        "execute_query_one_async",
        "execute_query_all_async",
        "listen_notify",
    ],
)
async def test_missing_app_async(method_name):
    with pytest.raises(exceptions.MissingApp):
        # Some of this methods are not async but they'll raise
        # before the await is reached.
        await getattr(cli.MissingAppConnector(), method_name)()


@pytest.mark.parametrize(
    "method_name",
    [
        "open",
        "close",
    ],
)
def test_missing_app_async__pass(method_name):
    getattr(cli.MissingAppConnector(), method_name)()


@pytest.mark.parametrize(
    "method_name",
    [
        "open_async",
        "close_async",
    ],
)
async def test_missing_app_async__pass_async(method_name):
    await getattr(cli.MissingAppConnector(), method_name)()


def test_load_app(mocker):
    class MyConnector(connector.BaseConnector):
        def get_sync_connector(self) -> BaseConnector:
            return self

    mocker.patch(
        "procrastinate.app.App.from_path",
        return_value=app.App(connector=MyConnector()),
    )
    with pytest.raises(argparse.ArgumentError, match="is not async"):
        cli.load_app("foobar")
