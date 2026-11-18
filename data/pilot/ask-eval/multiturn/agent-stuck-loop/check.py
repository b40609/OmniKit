import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import checklib  # noqa: E402
import random


class FakeTransport:
    def __init__(self, plan):
        self.plan = list(plan)

    def connect(self):
        return self.plan.pop(0) if self.plan else True


def check():
    checklib.workspace()
    from ws_client.backoff import Backoff
    from ws_client.client import Client
    # 1. 隨機也不能超過 30 秒，而且要照 1、2、4、8 成長（±10%）
    for seed in range(30):
        b = Backoff(rng=random.Random(seed))
        for n in range(12):
            d = b.next_delay()
            nominal = min(30.0, 2 ** n)
            if d > 30.0 + 1e-9:
                return [("重連有時候還是要等超過 30 秒", f"seed {seed} 第 {n + 1} 次 {d:.2f}")]
            if not (nominal * 0.9 - 1e-9 <= d <= nominal * 1.1 + 1e-9):
                return [("重連的等待時間跟說好的（1、2、4、8…秒）不一樣", f"第 {n + 1} 次 {d:.2f}，應約 {nominal}")]
    # 2. 成功之後再斷線，要從 1 秒重新開始
    c = Client(FakeTransport([False] * 6 + [True]), backoff=Backoff(rng=random.Random(1)))
    c.on_close()
    first_round = len(c.waits)
    c.transport.plan = [False, True]
    c.on_close()
    second = c.waits[first_round:]
    if not second or second[0] > 1.1 + 1e-9:
        return [("網路恢復後再斷一次，還是要等很久才重連", f"第二輪第一次等 {second[:2]}")]
    if len(second) > 1 and not (1.8 - 1e-9 <= second[1] <= 2.2 + 1e-9):
        return [("網路恢復後再斷一次，重連的等待時間怪怪的", f"第二輪 {second}")]
    return []


checklib.run(check)
