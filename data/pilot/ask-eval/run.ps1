<#
.SYNOPSIS
問法庫（omnikit-ask）有它與沒它的對照評測。用 Claude Code 的 `claude plugin eval`。

.DESCRIPTION
把 engine/skills/omnikit-ask 與 cases/ 組成暫時的 plugin，跑每一題「有 plugin」與「沒有 plugin」兩組，
用 LLM 評分。結果與 HTML 報告寫在暫存資料夾，最後印出路徑。會花額度：11 題、各 2 次約 7 美元。

從桌面版對話裡跑時，會先拿掉 ANTHROPIC_、CLAUDE_ 開頭的環境變數，否則子程序會落到 Haiku。
報告不上傳（--no-publish）。

.EXAMPLE
pwsh -File data/pilot/ask-eval/run.ps1
pwsh -File data/pilot/ask-eval/run.ps1 -Case ux-merge -Runs 1
#>
param(
  [string]$Case,
  [int]$Runs = 2,
  [string]$JudgeModel = 'sonnet'
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$work = Join-Path ([IO.Path]::GetTempPath()) ("omnikit-ask-eval-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force "$work\.claude-plugin", "$work\skills" | Out-Null
Copy-Item "$repo\engine\skills\omnikit-ask" "$work\skills\" -Recurse
Copy-Item "$PSScriptRoot\cases" "$work\evals" -Recurse
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

