<#
OmniKit 安裝：把這台 Windows 電腦接上 OmniKit，可以重複執行。

1. 安裝固定版本的 skillshare、uv、gh 與 gitleaks：從 GitHub release 下載 zip，比對寫死的
   SHA256 後解壓；不改 PATH。這台已經有 uv 或 gh 就沿用。skillshare 會先試跑一次：
   公司電腦的防毒可能擋下它，被擋就停下來，說明怎麼放行。
2. fork 出來的 repo：把 data/omnikit.yaml 的 repo、owner、marketplace 改成 origin 指向的
   GitHub repo、profile 改回 default，並重新產生 marketplace 清單，避免跟原作者的 marketplace 撞名。
3. 第一次執行時初始化 skillshare，target 是 Claude Code 與 Codex。
4. 規則 = 安全底線（data/rules/baseline.md）+ profile（data/profiles/<名稱>/AGENTS.md），
   由 profiles.py 接到兩邊：Claude 用 import，Codex 用複製（第一次接上時，原本的
   ~/.codex/AGENTS.md 先備份）。沒指定也沒選過 profile 就用 default（下載、安裝前會先問）。
   engine/skills 裡的 skills 也連進 skillshare，同步到兩邊。
5. 依 data/mcp/packages.txt 全域安裝 MCP 用的 npm 套件（固定版本），
   再把 data/mcp/servers.yaml 設成 skillshare 的 MCP 來源，同步到兩邊。
6. 把 data/harness/claude-allow.txt 的權限規則補進 Claude Code 的使用者設定（只增不刪），
   並在 Claude Code 與 Codex 註冊開新對話提醒的 Stop hook（session_nudge.py）；
   Codex 要使用者在 /hooks 信任後才會執行。
7. 設定 git hook：commit 前驗證名冊；commit 或 pull 動到規則、MCP 或權限規則時，自動同步。
8. 檢查 OmniKit repo 的 git 身分。

這台原本沒有、由 OmniKit 裝上的工具、npm 套件與權限規則，會記在
%LOCALAPPDATA%\omnikit\install-record.json；uninstall.ps1 只移除這些。

裝好之後，開新 session 說「幫我設定 OmniKit」，omnikit-setup 會用簡短訪談建立自己的 profile。

參數：
  -ProfileName <名稱>  用 data/profiles/<名稱> 的個人規則，並記下來；之後重跑不用再指定。
  -Fresh               這台第一次接上 OmniKit 時使用：把 ~/.claude/CLAUDE.md 受管區塊以外的舊規則
                       備份後移除，避免新舊規則同時生效。
  -WhatIf              預覽：依這台目前的狀態列出會改動的地方，什麼都不做（不下載、不執行 skillshare）。

用法（Windows PowerShell 5.1 或 PowerShell 7）：
  powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\install.ps1 [-ProfileName <名稱>] [-Fresh] [-WhatIf]
#>
param([string]$ProfileName, [switch]$Fresh, [switch]$WhatIf)

$ErrorActionPreference = 'Stop'
# PowerShell 5.1 的下載進度條會讓 Invoke-WebRequest 慢很多
$ProgressPreference = 'SilentlyContinue'

# 固定版本：升級時連同 SHA256 一起改，來源是各版 release 公布的 checksum
$SkillshareVersion = '0.28.2'
$SkillshareSha256 = @{
  amd64 = '91496399264347d29ca92689195864803e69ede0fe5166b302639f2ac4ed31bb'
  arm64 = '83c4e1762f0cdba84c8aa715e805d9fabf39f6f72c6556b277438d5345405432'
}
$UvVersion = '0.13.7'
$UvSha256 = @{
  amd64 = '0cdc5b38fe5a8168ed6a25814f5ba43c21d313dd3187314fccb37b7cec46e021'
  arm64 = '505d9e65e7692bac3ddf98c66754aa26c5050c409c184af30a881a0a72cc85e3'
}
$GhVersion = '2.103.3'
$GhSha256 = @{
  amd64 = '98d0cfa794721665d7973dd728c78aff7bd836d58f10f6d7a03568eccb0a22e0'
  arm64 = '197211c98687d7770ac331fe8a3b6c198c389108c1536cdbedf659fe4703e484'
}
$GitleaksVersion = '8.30.1'
$GitleaksSha256 = @{
  amd64 = 'd29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e'
  arm64 = 'b95f5e4f5c425cedca7ee203d9afd29597e692c4924a12ed42f970537c72cc0f'
}

$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ProfilesPy = Join-Path $Repo 'engine\scripts\profiles.py'
$Arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
$BinDir = Join-Path $env:LOCALAPPDATA 'Programs\skillshare'
$Exe = Join-Path $BinDir 'skillshare.exe'
$UvDir = Join-Path $env:LOCALAPPDATA 'Programs\uv'
$UvExe = Join-Path $UvDir 'uv.exe'
$GhDir = Join-Path $env:LOCALAPPDATA 'Programs\gh'
$GhExe = Join-Path $GhDir 'gh.exe'
$GitleaksDir = Join-Path $env:LOCALAPPDATA 'Programs\gitleaks'
$GitleaksExe = Join-Path $GitleaksDir 'gitleaks.exe'
$ClaudeMd = Join-Path $env:USERPROFILE '.claude\CLAUDE.md'
$CodexMd = Join-Path $env:USERPROFILE '.codex\AGENTS.md'
$RecordFile = Join-Path $env:LOCALAPPDATA 'omnikit\install-record.json'
$BlockPattern = '(?s)<!-- omnikit:rules:begin -->.*?<!-- omnikit:rules:end -->'

function Invoke-Skillshare {
  & $Exe @args
  if ($LASTEXITCODE -ne 0) { throw "skillshare $($args -join ' ') 失敗（exit $LASTEXITCODE）" }
}

# 優先用 PATH 上的 uv，沒有就用 Install-Uv 裝的那一份
function Get-Uv {
  $onPath = (Get-Command uv -ErrorAction SilentlyContinue).Source
  if ($onPath) { return $onPath }
  return $UvExe
}

# 備份成 <檔名>.pre-omnikit；已經有同名備份就加上時間
function Backup-File($path) {
  $backup = "$path.pre-omnikit"
  if (Test-Path $backup) { $backup += '-' + (Get-Date -Format 'yyyyMMddHHmmss') }
  Copy-Item $path $backup
  return $backup
}

# 安裝紀錄：只累加不刪除；權限規則由 claude_allow.py 自己記
function Add-InstallRecord($key, $values) {
  $record = @{}
  if (Test-Path $RecordFile) {
    $json = [IO.File]::ReadAllText($RecordFile, [Text.Encoding]::UTF8) | ConvertFrom-Json
    foreach ($p in $json.PSObject.Properties) { $record[$p.Name] = @($p.Value) }
  }
  $record[$key] = @(@($record[$key]) + @($values) | Where-Object { $_ } | Select-Object -Unique)
  New-Item -ItemType Directory -Force -Path (Split-Path $RecordFile) | Out-Null
  [IO.File]::WriteAllText($RecordFile, (ConvertTo-Json -InputObject $record -Depth 3), (New-Object Text.UTF8Encoding($false)))
}

# 下載 release zip，SHA256 相符才把指定的執行檔放進 $dest；$dest 是這次新建的就記進安裝紀錄
function Install-PinnedZip($url, $sha256, $exeNames, $dest) {
  $existed = Test-Path $dest
  $tmp = Join-Path $env:TEMP ('omnikit-' + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $tmp | Out-Null
  try {
    $zip = Join-Path $tmp (Split-Path -Leaf $url)
    Write-Host "下載 $url"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip
    $hash = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower()
    if ($hash -ne $sha256) { throw "SHA256 不符：預期 $sha256，實際 $hash" }
    Expand-Archive -Path $zip -DestinationPath (Join-Path $tmp 'x') -Force
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    foreach ($name in $exeNames) {
      $found = Get-ChildItem -Recurse -File (Join-Path $tmp 'x') -Filter $name | Select-Object -First 1
      if (-not $found) { throw "zip 裡找不到 $name" }
      Copy-Item -Force $found.FullName (Join-Path $dest $name)
    }
    if (-not $existed) { Add-InstallRecord paths $dest }
  } finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
  }
}

# 公司電腦的防毒可能擋下 skillshare.exe：Trend Micro 的「新出現的程式」偵測，對從網路下載、
# 很少人用或剛發布的程式，執行前要使用者按允許，沒人按就擋下；而且可能第一次能跑、之後才開始擋。
# 被擋時後面每一步都會失敗，所以先試跑一次，跑不動就停下來說明怎麼放行。
# 用 .NET 直接啟動：PowerShell 7 用 & 啟動失敗時，回報的是不相干的 StandardOutputEncoding 錯誤，看不出被擋。
# 回傳 --version 的輸出；檔案不存在時回傳 $null
function Test-Skillshare {
  if (-not (Test-Path $Exe)) { return $null }
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $Exe
  $psi.Arguments = '--version'
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.CreateNoWindow = $true
  try {
    $p = [System.Diagnostics.Process]::Start($psi)
    $out = $p.StandardOutput.ReadToEnd()
    $p.WaitForExit()
    if ($p.ExitCode -eq 0) { return $out.Trim() }
    $reason = "exit $($p.ExitCode)"
  } catch {
    $e = $_.Exception
    while ($e.InnerException) { $e = $e.InnerException }
    $reason = $e.Message.Trim()
  }
  $hash = try { (Get-FileHash -Algorithm SHA256 $Exe).Hash } catch { '（讀不到）' }
  Write-Host ''
  Write-Host "skillshare 無法執行：$reason" -ForegroundColor Red
  Write-Host "公司電腦的防毒（例如 Trend Micro）可能擋下了 $Exe"
  Write-Host '  - 有跳出防毒的通知：選允許，再重跑 install.ps1。'
  Write-Host "  - 沒有通知可按，或允許後又被擋：請 IT 把這個檔案加進例外（SHA256：$hash），再重跑 install.ps1。"
  Write-Host '  說明見 README 常見問題：「公司電腦執行 skillshare 時「存取被拒」？」'
  exit 1
}

function Install-Skillshare {
  if ((Test-Skillshare) -match [regex]::Escape($SkillshareVersion)) {
    Write-Host "skillshare $SkillshareVersion 已安裝：$Exe"
    return
  }
  $url = "https://github.com/runkids/skillshare/releases/download/v$SkillshareVersion/skillshare_${SkillshareVersion}_windows_$Arch.zip"
  Install-PinnedZip $url $SkillshareSha256[$Arch] @('skillshare.exe') $BinDir
  Test-Skillshare | Out-Null
  Write-Host "已安裝 skillshare $SkillshareVersion：$Exe"
}

# 名冊驗證等 Python 腳本用 uv 執行
function Install-Uv {
  $onPath = Get-Command uv -ErrorAction SilentlyContinue
  if ($onPath) {
    Write-Host "沿用這台已有的 uv：$($onPath.Source)"
    return
  }
  if ((Test-Path $UvExe) -and ((& $UvExe --version 2>$null) -match [regex]::Escape($UvVersion))) {
    Write-Host "uv $UvVersion 已安裝：$UvExe"
    return
  }
  $triple = if ($Arch -eq 'arm64') { 'aarch64' } else { 'x86_64' }
  $url = "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-$triple-pc-windows-msvc.zip"
  Install-PinnedZip $url $UvSha256[$Arch] @('uv.exe', 'uvx.exe') $UvDir
  Write-Host "已安裝 uv $UvVersion：$UvExe"
}

# 建立 repo、開 GitHub Pages 這類 GitHub 操作由 agent 用 gh 完成，不必手動進網頁設定
function Install-Gh {
  $onPath = Get-Command gh -ErrorAction SilentlyContinue
  if ($onPath) {
    Write-Host "沿用這台已有的 gh：$($onPath.Source)"
    return
  }
  if ((Test-Path $GhExe) -and ((& $GhExe --version 2>$null) -match [regex]::Escape($GhVersion))) {
    Write-Host "gh $GhVersion 已安裝：$GhExe"
    return
  }
  $url = "https://github.com/cli/cli/releases/download/v$GhVersion/gh_${GhVersion}_windows_$Arch.zip"
  Install-PinnedZip $url $GhSha256[$Arch] @('gh.exe') $GhDir
  Write-Host "已安裝 gh $GhVersion：$GhExe"
}

# 公開 repo 的金鑰外洩檢查：pre-commit hook 用它掃這次要 commit 的變動
function Install-Gitleaks {
  if ((Test-Path $GitleaksExe) -and ((& $GitleaksExe version 2>$null) -match [regex]::Escape($GitleaksVersion))) {
    Write-Host "gitleaks $GitleaksVersion 已安裝：$GitleaksExe"
    return
  }
  $platform = if ($Arch -eq 'arm64') { 'arm64' } else { 'x64' }
  $url = "https://github.com/gitleaks/gitleaks/releases/download/v$GitleaksVersion/gitleaks_${GitleaksVersion}_windows_$platform.zip"
  Install-PinnedZip $url $GitleaksSha256[$Arch] @('gitleaks.exe') $GitleaksDir
  Write-Host "已安裝 gitleaks $GitleaksVersion：$GitleaksExe"
}

# fork 出來的 repo，看板連結與 marketplace 名稱要換成自己的；
# marketplace 撞名的話，兩個 marketplace 沒辦法同時加進 Claude Code
function Sync-RepoConfig {
  $url = git -C $Repo remote get-url origin
  if ($url -notmatch 'github\.com[:/]([^/]+)/([^/]+?)(\.git)?/?$') {
    Write-Warning "origin 不是 GitHub repo（$url），略過 data/omnikit.yaml 的設定"
    return
  }
  $owner = $Matches[1]
  $name = $Matches[2]
  $config = Join-Path $Repo 'data\omnikit.yaml'
  $text = [IO.File]::ReadAllText($config, [Text.Encoding]::UTF8)
  if ($text -match "(?m)^repo: $([regex]::Escape("$owner/$name"))\s*$") { return }
  $text = [regex]::Replace($text, '(?m)^repo: .*$', "repo: $owner/$name")
  $text = [regex]::Replace($text, '(?m)^owner: .*$', "owner: $owner")
  $text = [regex]::Replace($text, '(?m)^marketplace: .*$', "marketplace: omnikit-$($owner.ToLower())")
  # 看板展示的情境原本是原作者的 profile，fork 之後先用 default 的範本，有自己的 profile 再改
  $text = [regex]::Replace($text, '(?m)^profile: .*$', 'profile: default')
  [IO.File]::WriteAllText($config, $text, (New-Object Text.UTF8Encoding($false)))
  & (Get-Uv) run --quiet (Join-Path $Repo 'engine\scripts\build.py') --marketplace-only | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "build.py --marketplace-only 失敗（exit $LASTEXITCODE）" }
  Write-Host "已把 data/omnikit.yaml 與 marketplace 清單改成 $owner/$name，記得 commit"
}

function Initialize-Skillshare {
  $dir = Join-Path $env:APPDATA 'skillshare'
  if (-not (Test-Path (Join-Path $dir 'config.yaml'))) {
    $existed = Test-Path $dir
    Invoke-Skillshare init --no-copy --no-git --no-skill --targets claude,codex --no-tui
    if (-not $existed) { Add-InstallRecord paths $dir }
  }
  # 設定檔已存在時 init 不會重跑；舊設定缺 target（曾發生少了 codex）就在這裡補上
  $have = (& $Exe target list --json | ConvertFrom-Json).targets.name
  if ($LASTEXITCODE -ne 0) { throw "skillshare target list 失敗（exit $LASTEXITCODE）" }
  $want = [ordered]@{ claude = '.claude\skills'; codex = '.agents\skills' }
  foreach ($name in $want.Keys) {
    if ($name -notin $have) {
      Invoke-Skillshare target add $name (Join-Path $env:USERPROFILE $want[$name])
      Write-Host "已補上 skillshare target：$name"
    }
  }
}

# 規則由 profiles.py 接上（git hook 也用它）：Claude 的受管區塊 import 底線與 profile 兩份；
# Codex 不支援 import，接成一份 %LOCALAPPDATA%\omnikit\rules\AGENTS.md，再由 skillshare 複製。
# 第一次接上 Codex 時（skillshare 還沒有 rules-codex），原本的 ~/.codex/AGENTS.md 先備份
function Connect-Rules {
  $config = Join-Path $env:APPDATA 'skillshare\config.yaml'
  $managed = [IO.File]::ReadAllText($config, [Text.Encoding]::UTF8) -match '(?m)^\s*- name: rules-codex\s*$'
  if (-not $managed -and (Test-Path $CodexMd)) {
    Write-Host "已備份原本的 Codex 規則：$(Backup-File $CodexMd)"
  }
  $profileArgs = if ($ProfileName) { @('--set', $ProfileName) } else { @() }
  & (Get-Uv) run --quiet $ProfilesPy --codex @profileArgs
  if ($LASTEXITCODE -ne 0) { throw "profiles.py 失敗（exit $LASTEXITCODE）" }
}

# OmniKit 自己的 skills（engine/skills）連進 skillshare 的來源，再同步到兩邊；
# 目標資料夾用 SKILL.md 的 name（target_naming: standard），符合 Agent Skills 規格
function Connect-Skills {
  $config = Join-Path $env:APPDATA 'skillshare\config.yaml'
  $text = [IO.File]::ReadAllText($config, [Text.Encoding]::UTF8)
  if ($text -notmatch '(?m)^target_naming: standard\s*$') {
    if ($text -match '(?m)^target_naming: .*$') { $text = [regex]::Replace($text, '(?m)^target_naming: .*$', 'target_naming: standard') }
    else { $text = $text.TrimEnd() + "`ntarget_naming: standard`n" }
    [IO.File]::WriteAllText($config, $text, (New-Object Text.UTF8Encoding($false)))
  }
  if (-not (Test-Path (Join-Path $env:APPDATA 'skillshare\skills\_omnikit'))) {
    Invoke-Skillshare link (Join-Path $Repo 'engine\skills') --name _omnikit --enable
  }
  Invoke-Skillshare sync
}

# MCP server 用到的 npm 套件，全域安裝 packages.txt 指定的版本；已經是那個版本就略過
function Install-McpPackages {
  $specs = @(Get-Content -Encoding UTF8 (Join-Path $Repo 'data\mcp\packages.txt') |
    ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
  if (-not $specs) { return }
  if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Warning "找不到 npm，略過 MCP 套件：$($specs -join ', ')。請先安裝 Node.js LTS 再重跑。"
    return
  }
  # 不轉向 stderr：PowerShell 5.1 在 Stop 模式下會把原生指令的 stderr 當成錯誤丟出
  $installed = (npm ls -g --depth=0 --json | Out-String | ConvertFrom-Json).dependencies
  $missing = @($specs | Where-Object {
    $name, $version = $_ -split '@(?=[^@]+$)'
    -not ($installed.$name -and $installed.$name.version -eq $version)
  })
  if (-not $missing) { Write-Host "MCP 套件已是指定版本：$($specs -join ', ')"; return }
  # 只升級版本的不算 OmniKit 裝的，移除時保留
  $new = @($missing | ForEach-Object { ($_ -split '@(?=[^@]+$)')[0] } | Where-Object { -not $installed.$_ })
  npm install -g @missing
  if ($LASTEXITCODE -ne 0) { throw "npm install -g $($missing -join ' ') 失敗（exit $LASTEXITCODE）" }
  if ($new) { Add-InstallRecord npm $new }
  Write-Host "已安裝 MCP 套件：$($missing -join ', ')"
}

# skillshare 沒有設定指令，直接在 config.yaml 的 sources 補上 mcp；sync 會合併寫入，不覆蓋兩邊的其他設定
function Connect-Mcp {
  $config = Join-Path $env:APPDATA 'skillshare\config.yaml'
  $line = '  mcp: ' + (Join-Path $Repo 'data\mcp\servers.yaml')
  $text = [IO.File]::ReadAllText($config, [Text.Encoding]::UTF8)
  if ($text -match '(?m)^  mcp: .*$') { $text = [regex]::Replace($text, '(?m)^  mcp: .*$', { $line }) }
  else { $text = ([regex]'(?m)^sources:\r?\n').Replace($text, { param($m) $m.Value + $line + "`n" }, 1) }
  [IO.File]::WriteAllText($config, $text, (New-Object Text.UTF8Encoding($false)))
  Invoke-Skillshare sync mcp --no-tui
}

# Claude Code 免問的權限規則；JSON 交給 Python 改，PowerShell 5.1 的 ConvertTo-Json 會改掉原本的格式
function Grant-ClaudePermissions {
  & (Get-Uv) run --quiet (Join-Path $Repo 'engine\scripts\claude_allow.py')
  if ($LASTEXITCODE -ne 0) { throw "claude_allow.py 失敗（exit $LASTEXITCODE）" }
}

# Codex 的開新對話提醒 hook；TOML 交給 Python 改，寫入前會驗證沒動到其他設定。
# 只是提醒，失敗時警告就好，不擋後面的步驟
function Register-CodexHook {
  & (Get-Uv) run --quiet (Join-Path $Repo 'engine\scripts\codex_hooks.py')
  if ($LASTEXITCODE -ne 0) { Write-Warning "codex_hooks.py 失敗（exit $LASTEXITCODE），Codex 的開新對話提醒沒有註冊" }
}

# 只留下 OmniKit 的受管區塊；舊內容先備份
function Clear-OldClaudeRules {
  $text = [IO.File]::ReadAllText($ClaudeMd, [Text.Encoding]::UTF8)
  $block = [regex]::Match($text, $BlockPattern).Value
  if ($text.Trim() -eq $block) { return }
  $backup = Backup-File $ClaudeMd
  [IO.File]::WriteAllText($ClaudeMd, $block + "`n", (New-Object Text.UTF8Encoding($false)))
  Write-Host "已移除 CLAUDE.md 受管區塊以外的舊規則，備份在 $backup"
}

function Enable-GitHooks {
  git -C $Repo config core.hooksPath .githooks
}

function Test-GitIdentity {
  $email = git -C $Repo config user.email
  Write-Host "OmniKit 的 git 身分：$(git -C $Repo config user.name) <$email>"
  if ($email -notmatch '@users\.noreply\.github\.com$') {
    Write-Warning "這不是 GitHub noreply 信箱，commit 到公開 repo 會公開它。可以只在這個 repo 改設：git -C `"$Repo`" config user.email <noreply 信箱>"
  }
}

# -WhatIf：依這台目前的狀態列出會改動的地方，什麼都不做（不下載、不執行 skillshare）
function Show-InstallPlan {
  $plan = @()
  $tools = @(
    @{ Name = 'skillshare'; Version = $SkillshareVersion; Path = $Exe; Command = $null },
    @{ Name = 'uv'; Version = $UvVersion; Path = $UvExe; Command = 'uv' },
    @{ Name = 'gh'; Version = $GhVersion; Path = $GhExe; Command = 'gh' },
    @{ Name = 'gitleaks'; Version = $GitleaksVersion; Path = $GitleaksExe; Command = $null }
  )
  foreach ($t in $tools) {
    $onPath = $t.Command -and (Get-Command $t.Command -ErrorAction SilentlyContinue)
    if (-not $onPath -and -not (Test-Path $t.Path)) {
      $plan += "下載 $($t.Name) $($t.Version)，比對 SHA256 後放到 $(Split-Path $t.Path)（不改 PATH）"
    }
  }
  if (-not (Test-Path $Exe)) { $plan += '  skillshare 裝好先試跑一次；被公司電腦的防毒擋下就停在這裡，說明怎麼放行' }

  $url = git -C $Repo remote get-url origin
  $config = [IO.File]::ReadAllText((Join-Path $Repo 'data\omnikit.yaml'), [Text.Encoding]::UTF8)
  if ($url -match 'github\.com[:/]([^/]+)/([^/]+?)(\.git)?/?$' -and $config -notmatch "(?m)^repo: $([regex]::Escape("$($Matches[1])/$($Matches[2])"))\s*$") {
    $plan += "data/omnikit.yaml 改成 $($Matches[1])/$($Matches[2])、看板用的 profile 改回 default，重新產生 marketplace 清單"
  }

  $ssConfig = Join-Path $env:APPDATA 'skillshare\config.yaml'
  if (-not (Test-Path $ssConfig)) { $plan += '初始化 skillshare（設定在 %APPDATA%\skillshare），同步目標是 Claude Code 與 Codex' }

  $stateFile = Join-Path $env:LOCALAPPDATA 'omnikit\profile.json'
  $chosen = if (Test-Path $stateFile) { try { ([IO.File]::ReadAllText($stateFile) | ConvertFrom-Json).profile } catch { $null } }
  $name = if ($ProfileName) { $ProfileName } elseif ($chosen) { $chosen } else { 'default' }
  $note = if ($ProfileName -or $chosen) { '' } else { '（還沒選過，用預設：下載、安裝前會先問）' }
  $plan += "規則：安全底線 + profile「$name」$note"
  if (-not (Test-Path (Join-Path $Repo "data\profiles\$name\AGENTS.md"))) {
    $plan += "  找不到 data/profiles/$name/AGENTS.md，安裝會在這一步失敗"
  }
  $hasBlock = (Test-Path $ClaudeMd) -and ([IO.File]::ReadAllText($ClaudeMd, [Text.Encoding]::UTF8) -match $BlockPattern)
  $plan += "  ~/.claude/CLAUDE.md：$(if ($hasBlock) { '更新' } else { '在開頭加上' })受管區塊，import 底線與 profile；其他內容不動"
  $codexManaged = (Test-Path $ssConfig) -and ([IO.File]::ReadAllText($ssConfig, [Text.Encoding]::UTF8) -match '(?m)^\s*- name: rules-codex\s*$')
  if (-not $codexManaged -and (Test-Path $CodexMd)) {
    $plan += '  ~/.codex/AGENTS.md：先備份成 AGENTS.md.pre-omnikit，再換成底線與 profile 接在一起的副本'
  } else {
    $plan += '  ~/.codex/AGENTS.md：換成底線與 profile 接在一起的副本'
  }
  if ($Fresh) { $plan += '  ~/.claude/CLAUDE.md：受管區塊以外的舊規則先備份成 CLAUDE.md.pre-omnikit，再移除' }

  $skills = (Get-ChildItem -Directory (Join-Path $Repo 'engine\skills')).Name -join '、'
  $plan += "skills：把 $skills 同步到 ~/.claude/skills 與 ~/.agents/skills"
  $packages = @(Get-Content -Encoding UTF8 (Join-Path $Repo 'data\mcp\packages.txt') |
    ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
  if ($packages) { $plan += "npm 全域套件（沒裝或版本不同才裝）：$($packages -join '、')" }
  $servers = [regex]::Matches([IO.File]::ReadAllText((Join-Path $Repo 'data\mcp\servers.yaml'), [Text.Encoding]::UTF8),
    '(?m)^  ([A-Za-z0-9_-]+):\s*$') | ForEach-Object { $_.Groups[1].Value }
  if ($servers) { $plan += "MCP：把 $($servers -join '、') 合併寫入 ~/.claude.json 與 ~/.codex/config.toml，不動其他設定" }
  $allow = @(Get-Content -Encoding UTF8 (Join-Path $Repo 'data\harness\claude-allow.txt') |
    ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
  if ($allow) { $plan += "~/.claude/settings.json：權限免問清單補上 $($allow -join '、')（只增不刪）" }
  $plan += '開新對話提醒：加進 ~/.claude/settings.json 與 ~/.codex/config.toml 的 Stop hook（Codex 要到 /hooks 信任才會跑）'
  if ((git -C $Repo config --get core.hooksPath) -ne '.githooks') {
    $plan += '這個 repo 改用 .githooks：commit 前掃金鑰、驗證名冊；改到規則、MCP 等檔案時自動同步'
  }

  Write-Host '這是預覽，什麼都沒改。照這台目前的狀態，install.ps1 會：'
  # 兩個空白開頭的是上一項的細節，縮排顯示
  $plan | ForEach-Object { if ($_.StartsWith('  ')) { Write-Host "      $($_.Trim())" } else { Write-Host "  - $_" } }
  Write-Host ''
  Write-Host '拿掉 -WhatIf 再執行就會照做；每一項的說明見 README 的「安裝會改動哪些地方」。'
}

# 安裝完畫面上不會多出東西，告訴使用者怎麼確認接上了、接下來怎麼用
function Show-NextSteps {
  $text = [IO.File]::ReadAllText((Join-Path $Repo 'data\rules\baseline.md'), [Text.Encoding]::UTF8)
  $version = if ($text -match '規則版本：(\S+)') { $Matches[1] } else { 'data/rules/baseline.md 開頭的版本' }
  $name = & (Get-Uv) run --quiet $ProfilesPy --show
  Write-Host ''
  Write-Host "OmniKit 已接上 Claude Code 與 Codex（profile：$name），開新的 session 才會生效："
  Write-Host "  - 問「OmniKit 規則版本與 profile 是什麼？」，應該回答 $version 與 $name"
  if ($name -eq 'default') {
    Write-Host '  - 建立自己的 profile：開新 session 說「幫我設定 OmniKit」（Claude Code 也可以輸入 /omnikit-setup，Codex 輸入 $omnikit-setup），回答幾題就好' -ForegroundColor Yellow
  } else {
    Write-Host '  - 重新設定 profile：開新 session 說「幫我設定 OmniKit」'
  }
  Write-Host '  - 換 profile：重跑 install.ps1 -ProfileName <名稱>，或 uv run engine/scripts/profiles.py --set <名稱>'
  Write-Host '  - 評估新工具：Claude Code 輸入 /omnikit-eval，Codex 輸入 $omnikit-eval'
  Write-Host '  - 預設 plugin 不會自動安裝；安裝方式與其他說明見 README 的「裝好之後」'
}

if ($WhatIf) { Show-InstallPlan; return }

Install-Skillshare
Install-Uv
Install-Gh
Install-Gitleaks
Sync-RepoConfig
Initialize-Skillshare
Connect-Rules
Connect-Skills
Install-McpPackages
Connect-Mcp
Grant-ClaudePermissions
Register-CodexHook
if ($Fresh) { Clear-OldClaudeRules }
Enable-GitHooks
Test-GitIdentity
Show-NextSteps
