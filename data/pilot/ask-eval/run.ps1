<#
.SYNOPSIS
問法庫（omnikit-ask）有它與沒它的對照評測。用 Claude Code 的 `claude plugin eval`。

.DESCRIPTION
把 engine/skills/omnikit-ask 與 cases/ 組成暫時的 plugin，跑每一題「有 plugin」與「沒有 plugin」兩組，
用 LLM 評分。結果與 HTML 報告寫在暫存資料夾，最後印出路徑。
會花額度：2026-11-17 的 11 題、各 2 次約 7 美元；題目擴充到 79 題後，全跑各 2 次照比例估約 50 美元，
平常用 -Case 挑題或 -Runs 1。只跑 cases/；variants/ 與 negatives/ 目前只有 agy_eval.py（Gemini）會跑。

從桌面版對話裡跑時，會先拿掉 ANTHROPIC_、CLAUDE_ 開頭的環境變數，否則子程序會落到 Haiku。
報告不上傳（--no-publish）。

訓練題與保留題（-Split，2026-11-18 起）：holdout.txt 列的是保留題，預設不跑（-Split train）。
改問法庫時只看訓練題；保留題只在定案時用 -Split holdout 跑一次。-Case 點名到另一份的題目會直接停下來。
-List 只列出會跑的題目，不呼叫 claude。

.EXAMPLE
pwsh -File data/pilot/ask-eval/run.ps1
pwsh -File data/pilot/ask-eval/run.ps1 -Case ux-merge -Runs 1
pwsh -File data/pilot/ask-eval/run.ps1 -Split holdout -List
#>
param(
  [string]$Case,
  [int]$Runs = 2,
  [string]$JudgeModel = 'sonnet',
  [ValidateSet('train', 'holdout', 'all')][string]$Split = 'train',
  [switch]$List
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path "$PSScriptRoot\..\..\..").Path

$held = @(Get-Content "$PSScriptRoot\holdout.txt" -Encoding utf8 | ForEach-Object { $_.Trim() } |
  Where-Object { $_ -and -not $_.StartsWith('#') })
$all = @(Get-ChildItem "$PSScriptRoot\cases" -Directory | Where-Object { -not $_.Name.StartsWith('_') })
$picked = @($all | Where-Object {
    $isHeld = $held -contains $_.Name
    $Split -eq 'all' -or ($Split -eq 'holdout' -and $isHeld) -or ($Split -eq 'train' -and -not $isHeld)
  })
if ($Case -and -not ($picked.Name -contains $Case)) {
  if ($all.Name -contains $Case) { throw "$Case 不在 $Split（見 holdout.txt）；要跑請加 -Split all 或另一份" }
  throw "找不到題目 $Case"
}
if ($Case) { $picked = @($picked | Where-Object { $_.Name -eq $Case }) }
if ($List) {
  $picked | ForEach-Object { Write-Host "$(if ($held -contains $_.Name) { 'holdout' } else { 'train' })`t$($_.Name)" }
  Write-Host "cases ${Split}：$($picked.Count) 題"
  return
}

$work = Join-Path ([IO.Path]::GetTempPath()) ("omnikit-ask-eval-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force "$work\.claude-plugin", "$work\skills", "$work\evals" | Out-Null
Copy-Item "$repo\engine\skills\omnikit-ask" "$work\skills\" -Recurse
$picked | ForEach-Object { Copy-Item $_.FullName "$work\evals\" -Recurse }
Write-Host "題目：cases $Split 共 $($picked.Count) 題"
'{ "name": "omnikit-ask-eval", "version": "0.0.1", "description": "omnikit-ask 對照評測", "license": "MIT" }' |
  Set-Content "$work\.claude-plugin\plugin.json" -Encoding utf8

Get-ChildItem env: | Where-Object { $_.Name -like 'ANTHROPIC_*' -or $_.Name -like 'CLAUDE_*' -or $_.Name -eq 'CLAUDECODE' } |
  ForEach-Object { Remove-Item "env:$($_.Name)" }

$cliArgs = @('plugin', 'eval', '.', '--runs', $Runs, '-j', '4', '--judge-model', $JudgeModel, '--trust-plugin',
  '--no-publish', '--threshold', '0', '--json', "$work\result.json", '--report', "$work\report.html")
if ($Case) { $cliArgs += @('--case', $Case) }
Push-Location $work
try { & claude @cliArgs } finally { Pop-Location }
Write-Host "結果：$work\result.json"
Write-Host "報告：$work\report.html"

