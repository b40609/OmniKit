---
description: omnikit-ask 情境 arch-fragmented-code
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
---

訂單建立的流程被拆成十幾個小檔，每次要追一個欄位怎麼算出來的，都要從 controller 一路跳進四五層 service、helper 跟 factory，結果裡面好幾層都只是把參數轉傳過去而已。想把這塊整理到好讀一點，該從哪裡下手？
