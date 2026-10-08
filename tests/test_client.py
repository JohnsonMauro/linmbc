import sys

from linmbc.gui import client


class FakeQProcess:
    def __init__(self, execute_code: int) -> None:
        self.execute_code = execute_code
        self.calls: list[tuple] = []

    def execute(self, program, args):
        self.calls.append(("execute", program, args))
        return self.execute_code

    def startDetached(self, program, args):
        self.calls.append(("startDetached", program, args))
        return True, 1234


def test_start_daemon_uses_the_systemd_user_unit_when_installed(monkeypatch):
    fake = FakeQProcess(execute_code=0)
    monkeypatch.setattr(client, "QProcess", fake)

    assert client.start_daemon() is True
    assert fake.calls == [
        ("execute", "systemctl", ["--user", "--no-block", "start", "linmbc.service"])
    ]


def test_start_daemon_spawns_this_interpreter_when_the_unit_is_missing(monkeypatch):
    fake = FakeQProcess(execute_code=5)  # systemctl: unit not found
    monkeypatch.setattr(client, "QProcess", fake)

    assert client.start_daemon() is True
    assert fake.calls[-1] == ("startDetached", sys.executable, ["-m", "linmbc.daemon"])


def test_start_daemon_spawns_when_systemctl_is_absent(monkeypatch):
    fake = FakeQProcess(execute_code=-2)  # QProcess: program could not be started
    monkeypatch.setattr(client, "QProcess", fake)

    assert client.start_daemon() is True
    assert fake.calls[-1][0] == "startDetached"
