"""Testes de tomenotas.notify."""

from tomenotas.notify import Notifier


def test_send_chama_notify_send():
    chamadas = []
    notifier = Notifier(spawn=lambda cmd: chamadas.append(cmd))
    notifier.send("Título", "Corpo")
    assert chamadas == [["notify-send", "Título", "Corpo"]]


def test_notify_send_ausente_degrada_para_stderr(capsys):
    def spawn_quebrado(_cmd):
        raise FileNotFoundError

    notifier = Notifier(spawn=spawn_quebrado)
    notifier.send("Título", "Corpo")  # não deve levantar exceção
    assert "Título: Corpo" in capsys.readouterr().err
