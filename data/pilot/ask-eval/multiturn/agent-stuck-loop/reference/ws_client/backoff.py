import random


class Backoff:
    def __init__(self, base=1.0, cap=30.0, jitter=0.1, rng=None):
        self.base, self.cap, self.jitter = base, cap, jitter
        self.rng = rng or random.Random()
        self.attempt = 0

    def next_delay(self):
        delay = min(self.cap, self.base * (2 ** self.attempt))
        self.attempt += 1
        return min(self.cap, max(0.0, delay + delay * self.jitter * self.rng.uniform(-1, 1)))

    def reset(self):
        self.attempt = 0
