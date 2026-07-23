"""Notificações de desktop via notify-send (mesmo mecanismo dos scripts bash)."""

import subprocess
import sys


class Notifier:
    def __init__(self, spawn=subprocess.Popen):
        self._spawn = spawn

    def send(self, titulo: str, corpo: str) -> None:
        try:
            self._spawn(["notify-send", titulo, corpo])
        except FileNotFoundError:
            # Sem libnotify-bin instalado: degrada para o stderr em vez de
            # derrubar o daemon por causa de uma notificação.
            print(f"tomenotas: {titulo}: {corpo}", file=sys.stderr)
