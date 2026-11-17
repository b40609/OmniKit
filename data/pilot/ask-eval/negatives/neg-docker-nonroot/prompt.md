---
description: omnikit-ask 負例 neg-docker-nonroot
kind: negative
expect_fire: false
---

這個 Dockerfile 改成用非 root 使用者執行（使用者名稱 `app`，UID 1000）：

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "main.py"]
```
