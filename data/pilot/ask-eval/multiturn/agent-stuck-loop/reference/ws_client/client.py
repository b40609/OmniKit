"""看板的 WebSocket 連線。transport 由外部提供（測試時用假的）。"""
from .backoff import Backoff


class Client:
    def __init__(self, transport, backoff=None, sleep=None):
        self.transport = transport
        self.backoff = backoff or Backoff()
        self.sleep = sleep or (lambda s: None)
        self.connected = False
        self.waits = []

    def on_open(self):
        self.connected = True
        self.backoff.reset()

    def on_close(self):
        self.connected = False
        self.reconnect()

    def reconnect(self):
        while not self.connected:
            delay = self.backoff.next_delay()
            self.waits.append(delay)
            self.sleep(delay)
            if self.transport.connect():
                self.on_open()
