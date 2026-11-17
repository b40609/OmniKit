---
description: omnikit-ask 負例 neg-health-endpoint
kind: negative
expect_fire: false
---

在 Express 的 `app.js` 加一個 `GET /api/health`，回傳 `{ "status": "ok" }`，並用 supertest 補一個測試。
