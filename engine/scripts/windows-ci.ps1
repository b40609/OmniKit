<#
Windows 持續整合（FR-34）：在 Windows PowerShell 5.1 或 PowerShell 7 上，把 CI 的檢查與自我測試全部跑一遍，
而且故意放在不好處理的環境：

- 長路徑、含空白與中文的路徑：repo 複製到這樣的資料夾再跑（還沒 commit 的改動也一起帶過去）；TEMP、TMP 也指到
  這樣的資料夾，Python 自我測試的暫存資料夾都在裡面。install.ps1 -WhatIf 與訪談用的家目錄、%LOCALAPPDATA% 也是。
- 模擬中文 Windows（cp950）：受測的 PowerShell 用 cp950 讀原生指令的輸出（[Console]::OutputEncoding），
  Python 的標準輸入輸出預設編碼設成 cp950（PYTHONIOENCODING）。CI 沒辦法改系統語系，
  真實的 cp950 環境要到試點同事的電腦上確認。
- 防毒短暫鎖住 uv 剛建好的暫存執行檔時，只重試一次，並在結果標出來（FR-34）；其他失敗不重試。

跑的項目：
1. .github/workflows/validate.yml「名冊」job 裡的每一個 uv run（自我測試與名冊檢查），照原樣讀出來跑；
   那裡加了新的檢查，這裡就會跟著跑。
2. preflight.ps1 -SelfTest、install.ps1 -SelfTest：用跑這支腳本的同一個 PowerShell。
3. install.ps1 -WhatIf：假的家目錄裡有 Claude Code 與 Codex 的設定資料夾、repo 外的 profile，repo 裡另有一個
   舊版存的 profile；預覽要列出 profile 的位置與要搬的舊 profile。會連網做安裝前檢查，但什麼都不寫。
4. FR-38：先搬舊版存在 repo 裡的 profile，再照 omnikit-setup 的步驟跑一次訪談（scan → 預覽 → 寫入並套用）；
   每一步之後，在 repo 裡跑 git status 都跟開始時一樣，看不到個人檔案。

不會動到這台的設定：從第 1 步起，家目錄與 %LOCALAPPDATA% 都換成測試資料夾裡假的，結束就換回來；
受測的腳本只加 -SelfTest 或 -WhatIf 這類開關，不會真的安裝。測試資料夾最後刪掉（-Keep 留著）。
結束碼：全部通過是 0，有失敗是 1。

用法：
  powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\windows-ci.ps1
  pwsh -NoProfile -File engine\scripts\windows-ci.ps1 [-Base <資料夾>] [-Length 160] [-Keep]
#>
param([string]$Base, [int]$Length = 160, [switch]$Keep)

# 每一步自己看結束碼；Stop 會讓 PowerShell 5.1 把原生指令寫到 stderr 的訊息當成錯誤丟出
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
# 這支腳本自己的輸出用 UTF-8，CI 的紀錄才看得懂；受測的子行程另外設成 cp950
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false) } catch { }
$OutputEncoding = New-Object Text.UTF8Encoding($false)
$Cp950 = [Text.Encoding]::GetEncoding(950)
$Utf8 = New-Object Text.UTF8Encoding($false)
$PsExe = (Get-Process -Id $PID).Path
$Source = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:Results = New-Object System.Collections.ArrayList

function Add-Result($name, $ok, $detail) {
  [void]$script:Results.Add([pscustomobject]@{ Name = $name; Ok = [bool]$ok })
  $mark = if ($ok) { '通過' } else { '失敗' }
  $suffix = if ($detail) { "：$detail" } else { '' }
  Write-Host "[$mark] $name$suffix"
}

function Write-File($path, $text) {
  New-Item -ItemType Directory -Force -Path (Split-Path $path) | Out-Null
  [IO.File]::WriteAllText($path, $text, $Utf8)
}

# 受測的 PowerShell 用 cp950 寫輸出，Python 直接寫 UTF-8：逐行先當 UTF-8 解，不是合法的 UTF-8 才當 cp950
function ConvertFrom-MixedBytes([byte[]]$bytes) {
  $strict = New-Object Text.UTF8Encoding($false, $true)
  $lines = New-Object System.Collections.ArrayList
  $start = 0
  for ($i = 0; $i -le $bytes.Length; $i++) {
    if ($i -eq $bytes.Length -or $bytes[$i] -eq 10) {
      $chunk = New-Object byte[] ($i - $start)
      [Array]::Copy($bytes, $start, $chunk, 0, $chunk.Length)
      try { [void]$lines.Add($strict.GetString($chunk)) } catch { [void]$lines.Add($Cp950.GetString($chunk)) }
      $start = $i + 1
    }
  }
  return ($lines -join "`n").Replace("`r", '')
}

# 用跟這支腳本同一個 PowerShell 跑受測的腳本，並且像中文 Windows 一樣用 cp950 讀原生指令的輸出。
# $switches 原樣接在後面（例如 -SelfTest）：加了引號就變成字串，會被當成 install.ps1 的 -ProfileName，變成真的安裝。
# -Plan：腳本正常結束（沒有丟出錯誤）就算成功；install.ps1 -WhatIf 的結束碼是安裝前檢查的，CI 機器不一定全過
function Invoke-Child([string]$script, [ValidatePattern('^(-[A-Za-z]+\s*)+$')][string]$switches, [switch]$Plan) {
  $call = "& '$($script -replace "'", "''")' $switches"
  $prefix = '$e = [Text.Encoding]::GetEncoding(950); try { [Console]::OutputEncoding = $e } catch { }; $OutputEncoding = $e; '
  $body = if ($Plan) { "try { $call; exit 0 } catch { Write-Host `$_; exit 1 }" } else { "$call; exit `$LASTEXITCODE" }
  $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($prefix + $body))
  $out = Join-Path $Temp ('child-' + [guid]::NewGuid().ToString('N') + '.txt')
  $err = "$out.err"
  $p = Start-Process -FilePath $PsExe -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $encoded) `
    -RedirectStandardOutput $out -RedirectStandardError $err -NoNewWindow -Wait -PassThru
  $p.WaitForExit()
  $text = (ConvertFrom-MixedBytes ([IO.File]::ReadAllBytes($out))) + "`n" + (ConvertFrom-MixedBytes ([IO.File]::ReadAllBytes($err)))
  Remove-Item -Force $out, $err -ErrorAction SilentlyContinue
  Write-Host $text.Trim()
  return @{ Code = $p.ExitCode; Output = $text }
}

function Get-Status { return ((git -C $Repo status --porcelain --untracked-files=all) -join "`n") }

# 防毒（例如 Trend Micro）會短暫鎖住 uv 剛在 TEMP 建好的執行檔（uv-trampoline-*.exe），uv 回報
# 「Failed to update Windows PE resources」或 os error 32。只有這類錯誤等 3 秒重試一次（FR-34），其他失敗不重試；
# 重試過的會標在結果裡。stdout 與 stderr 分開收，stdout 才能直接當 JSON 讀
$TransientUv = 'Failed to update Windows PE resources|os error 32\b|being used by another process'
function Invoke-Uv([string[]]$arguments, [string]$stdin) {
  $errFile = Join-Path $Temp ('uv-' + [guid]::NewGuid().ToString('N') + '.err')
  for ($try = 1; $try -le 2; $try++) {
    if ($PSBoundParameters.ContainsKey('stdin')) { $out = @($stdin | & uv @arguments 2> $errFile) } else { $out = @(& uv @arguments 2> $errFile) }
    $code = $LASTEXITCODE
    $err = if (Test-Path -LiteralPath $errFile) { ((Get-Content -LiteralPath $errFile) | ForEach-Object { "$_" }) -join "`n" } else { '' }
    if ($code -eq 0 -or $try -eq 2 -or $err -notmatch $TransientUv) { break }
    Write-Host "uv 的暫存執行檔被鎖住（多半是防毒在掃描），3 秒後重試：uv $($arguments -join ' ')"
    Start-Sleep -Seconds 3
  }
  Remove-Item -LiteralPath $errFile -ErrorAction SilentlyContinue
  return @{ Code = $code; Output = ($out -join "`n"); Error = $err; Retried = ($try -gt 1) }
}

function Get-Detail($r) {
  $parts = @()
  if ($r.Code -ne 0) { $parts += "exit $($r.Code)" }
  if ($r.Retried) { $parts += '防毒鎖住 uv 的暫存執行檔，重試一次' }
  return ($parts -join '；')
}

# ---- 0. 準備：長路徑、含空白與中文的資料夾 ----

$root = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
# 最後要刪的資料夾：自己產生的就連補長度用的外層一起刪
$Cleanup = $Base
if (-not $Base) {
  $Base = Join-Path $root ('OmniKit CI 王小明 的 資料夾 ' + [guid]::NewGuid().ToString('N').Substring(0, 6))
  $Cleanup = $Base
  $pad = $Length - $Base.Length - 1
  if ($pad -gt 3) { $Base = Join-Path $Base ('長路徑 ' + ('x' * ($pad - 4))) }
}
$Repo = Join-Path $Base 'OmniKit 副本'
$Temp = Join-Path $Base '暫存 tmp'
$FakeHome = Join-Path $Base '使用者 家目錄'
$FakeLocal = Join-Path $FakeHome 'AppData\Local'
$UvCache = (& uv cache dir | Out-String).Trim()
New-Item -ItemType Directory -Force -Path $Repo, $Temp, $FakeLocal | Out-Null

Write-Host "PowerShell $($PSVersionTable.PSVersion)（$PsExe）"
Write-Host "測試資料夾（$($Base.Length) 字元）：$Base"

# repo 複製過去：commit 過的與還沒 commit 的檔案都帶著（.gitignore 排除的不帶），再建一個只有暫存區的 git repo，
# 讓「有沒有進版本控制」與 git status 都能判斷。origin 指向公開 repo，跟同事 clone 下來的一樣
$files = @(git -C $Source -c core.quotepath=off ls-files --cached --others --exclude-standard |
    Where-Object { $_ -and (Test-Path -LiteralPath (Join-Path $Source $_) -PathType Leaf) })
foreach ($rel in $files) {
  $dest = Join-Path $Repo $rel
  New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
  [IO.File]::Copy((Join-Path $Source $rel), $dest, $true)
}
git init --quiet $Repo
git -C $Repo -c core.autocrlf=false -c core.longpaths=true add -A
git -C $Repo remote add origin https://github.com/b40609/OmniKit.git
$longest = ($files | ForEach-Object { (Join-Path $Repo $_).Length } | Measure-Object -Maximum).Maximum
Add-Result "複製 repo 到測試資料夾（$($files.Count) 個檔案，最長的路徑 $longest 字元）" ($files.Count -gt 50 -and (Test-Path (Join-Path $Repo 'engine\scripts\install.ps1')))
$StatusCopied = Get-Status

# 從這裡開始，家目錄與 %LOCALAPPDATA% 都換成測試資料夾裡假的，碰不到這台的設定；結束時換回來。
# uv 的快取指回原本的，免得重新下載
$savedEnv = @{}
foreach ($k in 'TEMP', 'TMP', 'PYTHONIOENCODING', 'USERPROFILE', 'HOME', 'LOCALAPPDATA', 'UV_CACHE_DIR') {
  $savedEnv[$k] = [Environment]::GetEnvironmentVariable($k)
}
$env:TEMP = $Temp
$env:TMP = $Temp
$env:PYTHONIOENCODING = 'cp950'
$env:UV_CACHE_DIR = $UvCache
$env:USERPROFILE = $FakeHome
$env:HOME = $FakeHome
$env:LOCALAPPDATA = $FakeLocal
try {

# ---- 1. validate.yml「名冊」job 的每一個 uv run ----

$commands = @()
$job = $null
foreach ($line in (Get-Content -LiteralPath (Join-Path $Repo '.github\workflows\validate.yml') -Encoding UTF8)) {
  if ($line -match '^  ([A-Za-z0-9_-]+):\s*$') { $job = $Matches[1]; continue }
  if ($job -eq 'validate' -and $line -match '^\s+- run: (uv run .+?)\s*$') { $commands += $Matches[1] }
}
Add-Result "讀到 validate.yml 的檢查：$($commands.Count) 個" ($commands.Count -ge 20)
foreach ($cmd in $commands) {
  # bash 的 > /dev/null 換成 PowerShell 的丟掉輸出
  $discard = $cmd -match '\s>\s*/dev/null$'
  $line = $cmd -replace '\s>\s*/dev/null$', ''
  $tokens = @($line -split '\s+' | Where-Object { $_ })
  Write-Host "::group::$line"
  Push-Location -LiteralPath $Repo
  try { $r = Invoke-Uv @($tokens | Select-Object -Skip 1) } finally { Pop-Location }
  if (-not $discard -and $r.Output) { Write-Host $r.Output }
  if ($r.Error) { Write-Host $r.Error }
  Write-Host '::endgroup::'
  Add-Result $line ($r.Code -eq 0) (Get-Detail $r)
}

# ---- 2. PowerShell 腳本的自我測試 ----

foreach ($name in 'preflight.ps1', 'install.ps1') {
  Write-Host "::group::$name -SelfTest"
  $r = Invoke-Child (Join-Path $Repo "engine\scripts\$name") '-SelfTest'
  Write-Host '::endgroup::'
  Add-Result "$name -SelfTest" ($r.Code -eq 0 -and $r.Output -match '全部通過') "exit $($r.Code)"
}

$StatusBefore = Get-Status
Add-Result '自我測試沒有在 repo 裡留下檔案（git status 跟剛複製好時一樣）' ($StatusBefore -eq $StatusCopied)

# ---- 3. install.ps1 -WhatIf：假的家目錄，profile 在 repo 外，repo 裡另有一個舊版存的 ----

Write-File (Join-Path $FakeHome '.claude\CLAUDE.md') "# 我自己的規則`n"
New-Item -ItemType Directory -Force -Path (Join-Path $FakeHome '.codex') | Out-Null
$colleague = Join-Path $FakeLocal 'omnikit\profiles\ci-colleague'
Write-File (Join-Path $colleague 'AGENTS.md') "# 個人規則：ci-colleague`n"
Write-File (Join-Path $colleague 'answers.json') '{"name": "ci-colleague", "evaluate_tools": false}'
Write-File (Join-Path $FakeLocal 'omnikit\profile.json') '{"profile": "ci-colleague"}'
$legacy = Join-Path $Repo 'data\profiles\ci-legacy'
Write-File (Join-Path $legacy 'AGENTS.md') "# 舊版存在 repo 裡的 profile`n"
Write-File (Join-Path $legacy 'answers.json') '{"name": "ci-legacy"}'

Write-Host '::group::install.ps1 -WhatIf'
$r = Invoke-Child (Join-Path $Repo 'engine\scripts\install.ps1') '-WhatIf' -Plan
Write-Host '::endgroup::'
Add-Result 'install.ps1 -WhatIf：正常列出預覽' ($r.Code -eq 0 -and $r.Output.Contains('這是預覽，什麼都沒改')) "exit $($r.Code)"
Add-Result 'install.ps1 -WhatIf：profile 在 repo 外，列出位置' ($r.Output.Contains("profile「ci-colleague」") -and $r.Output.Contains($colleague))
Add-Result 'install.ps1 -WhatIf：列出舊版存在 repo 裡、要搬的 profile' ($r.Output.Contains('舊版存在 repo 裡的 profile（ci-legacy）'))
Add-Result 'install.ps1 -WhatIf：照 repo 外 profile 的答案預覽 skills' ($r.Output.Contains('不裝 omnikit-eval'))
Add-Result 'install.ps1 -WhatIf：什麼都沒寫' ((Get-Content -LiteralPath (Join-Path $FakeHome '.claude\CLAUDE.md') -Raw -Encoding UTF8) -eq "# 我自己的規則`n" -and
  -not (Test-Path (Join-Path $FakeLocal 'omnikit\agents.json')) -and (Test-Path $legacy))

# ---- 4. FR-38：搬舊版的 profile、跑一次訪談，git status 都跟開始時一樣 ----

$profilesPy = Join-Path $Repo 'engine\scripts\profiles.py'
$setupPy = Join-Path $Repo 'engine\skills\omnikit-setup\scripts\setup.py'
Write-Host '::group::FR-38：搬舊版存在 repo 裡的 profile'
# stdin 給空的：不能互動，跟 agent 在背景跑 install.ps1 一樣
$r = Invoke-Uv @('run', '--quiet', $profilesPy, '--migrate') -stdin ''
Write-Host $r.Output $r.Error
Add-Result 'FR-38：舊版 profile，不能互動又沒同意：只列出來，什麼都不改' ($r.Code -eq 0 -and (Test-Path $legacy) -and
  $r.Output.Contains('--migrate --yes')) (Get-Detail $r)
$r = Invoke-Uv @('run', '--quiet', $profilesPy, '--migrate', '--yes')
Write-Host $r.Output $r.Error
Write-Host '::endgroup::'
Add-Result 'FR-38：同意後搬到 repo 外，repo 的 git status 回到開始時' ($r.Code -eq 0 -and -not (Test-Path $legacy) -and
  (Test-Path (Join-Path $FakeLocal 'omnikit\profiles\ci-legacy\answers.json')) -and (Get-Status) -eq $StatusBefore) (Get-Detail $r)

Write-Host '::group::FR-38：訪談（scan → 預覽 → 寫入並套用）'
$r = Invoke-Uv @('run', '--quiet', $setupPy, 'scan')
$scan = $r.Output | ConvertFrom-Json
$answers = $scan.omnikit.answers_file
Add-Result 'FR-38：scan 的答案檔與 profile 位置都在 repo 外' ($answers.StartsWith($FakeLocal) -and
  $scan.omnikit.profiles_dir -eq (Join-Path $FakeLocal 'omnikit\profiles'))
Write-File $answers ('{"name": "wang-xiaoming", "language": "zh-TW", "verbosity": "concise", "autonomy": "balanced", ' +
  '"work": ["coding", "data"], "pains": ["no-verification"], "background": "產線資料分析，Python", ' +
  '"projects": {"main": "產線 監控"}, "evaluate_tools": true}')
$r = Invoke-Uv @('run', '--quiet', $setupPy, 'profile', '--answers', $answers)
Write-Host $r.Output $r.Error
$preview = $r.Code
$r = Invoke-Uv @('run', '--quiet', $setupPy, 'profile', '--answers', $answers, '--write', '--apply')
Write-Host $r.Output $r.Error
$written = $r.Code
Write-Host '::endgroup::'
$folder = Join-Path $FakeLocal 'omnikit\profiles\wang-xiaoming'
Add-Result 'FR-38：訪談寫進 repo 外的 profile 資料夾' ($preview -eq 0 -and $written -eq 0 -and
  (Test-Path (Join-Path $folder 'AGENTS.md')) -and (Test-Path (Join-Path $folder 'answers.json')) -and (Test-Path (Join-Path $folder 'scenarios.yaml')))
Add-Result 'FR-38：訪談跑完，repo 的 git status 跟開始時一樣（看不到個人檔案）' ((Get-Status) -eq $StatusBefore)
$imports = @((Get-Content -LiteralPath (Join-Path $FakeHome '.claude\CLAUDE.md') -Encoding UTF8) | Where-Object { $_.StartsWith('@') })
# 依序是安全底線、共用分派（data/rules/dispatch.md）、個人 AGENTS.md；個人 dispatch.md 有才接，這裡沒有
Add-Result 'Claude import：路徑有空白與中文時，空白用反斜線跳脫，指到 repo 外的 profile' ($imports.Count -eq 3 -and
  $imports[0].EndsWith('/rules/baseline.md') -and $imports[1].EndsWith('/rules/dispatch.md') -and
  -not ($imports | Where-Object { $_ -match '(?<!\\) ' }) -and $imports[2].EndsWith('/omnikit/profiles/wang-xiaoming/AGENTS.md') -and
  $imports[2].Contains('使用者\ 家目錄'))

} finally {
  foreach ($k in $savedEnv.Keys) { [Environment]::SetEnvironmentVariable($k, $savedEnv[$k]) }
}

# ---- 結果 ----

$failed = @($script:Results | Where-Object { -not $_.Ok })
Write-Host ''
Write-Host "PowerShell $($PSVersionTable.PSVersion)：$($script:Results.Count) 項，失敗 $($failed.Count) 項"
foreach ($f in $failed) { Write-Host "  失敗：$($f.Name)" }
if (-not $Keep) {
  Remove-Item -Recurse -Force -LiteralPath $Cleanup -ErrorAction SilentlyContinue
  if (Test-Path -LiteralPath $Cleanup) { Write-Warning "測試資料夾沒有刪乾淨：$Cleanup" }
} else {
  Write-Host "測試資料夾留著：$Base"
}
exit $(if ($failed.Count) { 1 } else { 0 })
