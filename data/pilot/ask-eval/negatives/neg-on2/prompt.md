---
description: omnikit-ask 負例 neg-on2
kind: negative
expect_fire: false
---

這段 Python 是 O(n²)，幫我改成 O(n)：

```python
def has_dup(xs):
    for i in range(len(xs)):
        for j in range(i + 1, len(xs)):
            if xs[i] == xs[j]:
                return True
    return False
```
