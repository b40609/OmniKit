<#
OmniKit 安裝：把這台 Windows 電腦接上 OmniKit，可以重複執行。

接上的 agent 是偵測到的 Claude Code、Codex 與 Antigravity。全部由 OmniKit 自己的 Python 腳本接，
不經過 skillshare：公司電腦的防毒會擋下 skillshare（允許的通知要剛好盯著畫面才按得到）。

1. 安裝固定版本的 uv、gh 與 gitleaks：從 GitHub release 下載 zip，比對寫死的 SHA256 後解壓；
   不改 PATH。這台已經有 uv 或 gh 就沿用。
2. fork 出來的 repo：把 data/omnikit.yaml 的 repo、owner、marketplace 改成 origin 指向的
   GitHub repo、profile 改回 default，並重新產生 marketplace 清單，避免跟原作者的 marketplace 撞名。
3. 依 data/mcp/packages.txt 全域安裝 MCP 用的 npm 套件（固定版本）。
4. agents.py connect：
   - 規則 = 安全底線（data/rules/baseline.md）+ profile（data/profiles/<名稱>/AGENTS.md）。
     Claude 在 ~/.claude/CLAUDE.md 用受管區塊 import；Codex 整份換掉 ~/.codex/AGENTS.md；
     Antigravity 在 ~/.gemini/GEMINI.md 加受管區塊（原地改寫，硬連結不會斷）。Codex 與 Antigravity
     原本的規則先備份成 .pre-omnikit。沒指定也沒選過 profile 就用 default（下載、安裝前會先問）。
   - skills：engine/skills 連到 ~/.claude/skills；複製到 ~/.agents/skills 給 Codex 與 Antigravity。
   - MCP：data/mcp/servers.yaml 寫進三邊的設定，不動其他設定。
   - 舊版用 skillshare 接的，改由 OmniKit 接手，並拿掉 skillshare 設定裡 OmniKit 的部分（skillshare 本身不刪）。
5. 把 data/harness/claude-allow.txt 的權限規則補進 Claude Code 的使用者設定（只增不刪），
   並在 Claude Code 與 Codex 註冊開新對話提醒的 Stop hook（session_nudge.py）；
   Codex 要使用者在 /hooks 信任後才會執行。
6. 設定 git hook：commit 前驗證名冊；commit 或 pull 動到規則、skills、MCP 或權限規則時，自動同步。
7. 檢查 OmniKit repo 的 git 身分。

這台原本沒有、由 OmniKit 裝上的工具、npm 套件與權限規則，會記在
%LOCALAPPDATA%\omnikit\install-record.json；接上了哪些 agent、管了哪些 skills 與 MCP，記在
%LOCALAPPDATA%\omnikit\agents.json。uninstall.ps1 只移除這些。

裝好之後，開新 session 說「幫我設定 OmniKit」，omnikit-setup 會用簡短訪談建立自己的 profile。

參數：
  -ProfileName <名稱>  用 data/profiles/<名稱> 的個人規則，並記下來；之後重跑不用再指定。
  -Fresh               這台第一次接上 OmniKit 時使用：把 ~/.claude/CLAUDE.md 受管區塊以外的舊規則
                       備份後移除，避免新舊規則同時生效。
  -WhatIf              預覽：依這台目前的狀態列出會改動的地方，什麼都不做（不下載、不寫檔）。

用法（Windows PowerShell 5.1 或 PowerShell 7）：
  powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\install.ps1 [-ProfileName <名稱>] [-Fresh] [-WhatIf]
#>
param([string]$ProfileName, [switch]$Fresh, [switch]$WhatIf)

$ErrorActionPreference = 'Stop'
# PowerShell 5.1 的下載進度條會讓 Invoke-WebRequest 慢很多
$ProgressPreference = 'SilentlyContinue'

# 固定版本：升級時連同 SHA256 一起改，來源是各版 release 公布的 checksum
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
$AgentsPy = Join-Path $Repo 'engine\scripts\agents.py'
$Arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
$UvDir = Join-Path $env:LOCALAPPDATA 'Programs\uv'
$UvExe = Join-Path $UvDir 'uv.exe'
$GhDir = Join-Path $env:LOCALAPPDATA 'Programs\gh'
$GhExe = Join-Path $GhDir 'gh.exe'
$GitleaksDir = Join-Path $env:LOCALAPPDATA 'Programs\gitleaks'
$GitleaksExe = Join-Path $GitleaksDir 'gitleaks.exe'
$ClaudeMd = Join-Path $env:USERPROFILE '.claude\CLAUDE.md'
$CodexMd = Join-Path $env:USERPROFILE '.codex\AGENTS.md'
$GeminiMd = Join-Path $env:USERPROFILE '.gemini\GEMINI.md'
$AgentsFile = Join-Path $env:LOCALAPPDATA 'omnikit\agents.json'
$RecordFile = Join-Path $env:LOCALAPPDATA 'omnikit\install-record.json'
$SkillshareConfig = Join-Path $env:APPDATA 'skillshare\config.yaml'
$BlockPattern = '(?s)<!-- omnikit:rules:begin -->.*?<!-- omnikit:rules:end -->'
$OursHeader = '<!-- 由 OmniKit 產生，不要手改：'
$AgentNames = [ordered]@{ 'claude-code' = 'Claude Code'; 'codex' = 'Codex'; 'antigravity' = 'Antigravity' }

# 優先用 PATH 上的 uv，沒有就用 Install-Uv 裝的那一份
function Get-Uv {
  $onPath = (Get-Command uv -ErrorAction SilentlyContinue).Source
  if ($onPath) { return $onPath }
  return $UvExe
}

function Get-FileText($path) { if (Test-Path $path) { [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8) } else { '' } }

# 跟 agents.py 的 detect 一樣：看設定資料夾或 PATH 上的指令
function Get-Agents {
  $has = { param($dirs, $commands)
    foreach ($d in $dirs) { if (Test-Path (Join-Path $env:USERPROFILE $d)) { return $true } }
    foreach ($c in $commands) { if (Get-Command $c -ErrorAction SilentlyContinue) { return $true } }
    return $false
  }
  $found = @()
  if (& $has @('.claude') @('claude')) { $found += 'claude-code' }
  if (& $has @('.codex') @('codex')) { $found += 'codex' }
  if (& $has @('.gemini\config', '.gemini\antigravity') @('agy', 'antigravity')) { $found += 'antigravity' }
  return $found
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

# 名冊驗證、接上 agent 等 Python 腳本用 uv 執行
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

# 規則、skills、MCP 都交給 agents.py（git hook 也用它同步）
function Connect-Agents {
  $profileArgs = if ($ProfileName) { @('--profile', $ProfileName) } else { @() }
  & (Get-Uv) run --quiet $AgentsPy connect @profileArgs
  if ($LASTEXITCODE -ne 0) { throw "agents.py connect 失敗（exit $LASTEXITCODE）" }
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

# -WhatIf：依這台目前的狀態列出會改動的地方，什麼都不做（不下載、不寫檔）
function Show-InstallPlan {
  $plan = @()
  $tools = @(
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

  $url = git -C $Repo remote get-url origin
  $config = [IO.File]::ReadAllText((Join-Path $Repo 'data\omnikit.yaml'), [Text.Encoding]::UTF8)
  if ($url -match 'github\.com[:/]([^/]+)/([^/]+?)(\.git)?/?$' -and $config -notmatch "(?m)^repo: $([regex]::Escape("$($Matches[1])/$($Matches[2])"))\s*$") {
    $plan += "data/omnikit.yaml 改成 $($Matches[1])/$($Matches[2])、看板用的 profile 改回 default，重新產生 marketplace 清單"
  }
  $packages = @(Get-Content -Encoding UTF8 (Join-Path $Repo 'data\mcp\packages.txt') |
    ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
  if ($packages) { $plan += "npm 全域套件（沒裝或版本不同才裝）：$($packages -join '、')" }

  $agents = @(Get-Agents)
  if (-not $agents) {
    $plan += '找不到 Claude Code、Codex 或 Antigravity，安裝會在接上 agent 這一步失敗'
  } else {
    $plan += "接上偵測到的 agent：$(($agents | ForEach-Object { $AgentNames[$_] }) -join '、')"
  }
  $stateFile = Join-Path $env:LOCALAPPDATA 'omnikit\profile.json'
  $chosen = if (Test-Path $stateFile) { try { ([IO.File]::ReadAllText($stateFile) | ConvertFrom-Json).profile } catch { $null } }
  $name = if ($ProfileName) { $ProfileName } elseif ($chosen) { $chosen } else { 'default' }
  $note = if ($ProfileName -or $chosen) { '' } else { '（還沒選過，用預設：下載、安裝前會先問）' }
  $plan += "  規則：安全底線 + profile「$name」$note"
  if (-not (Test-Path (Join-Path $Repo "data\profiles\$name\AGENTS.md"))) {
    $plan += "  找不到 data/profiles/$name/AGENTS.md，安裝會在這一步失敗"
  }
  if ($agents -contains 'claude-code') {
    $verb = if ((Get-FileText $ClaudeMd) -match $BlockPattern) { '更新' } else { '在開頭加上' }
    $plan += "  ~/.claude/CLAUDE.md：$($verb)受管區塊，import 底線與 profile；其他內容不動"
  }
  if ($agents -contains 'codex') {
    $legacy = (Get-FileText $SkillshareConfig) -match '(?m)^\s*- name: rules-codex\s*$'
    $ours = (Get-FileText $CodexMd).TrimStart().StartsWith($OursHeader) -or $legacy
    if ((Test-Path $CodexMd) -and -not $ours) {
      $plan += '  ~/.codex/AGENTS.md：先備份成 AGENTS.md.pre-omnikit，再換成底線與 profile 接在一起的內容'
    } else {
      $plan += '  ~/.codex/AGENTS.md：換成底線與 profile 接在一起的內容'
    }
  }
  if ($agents -contains 'antigravity') {
    $gemini = Get-FileText $GeminiMd
    if ($gemini -match $BlockPattern) {
      $plan += '  ~/.gemini/GEMINI.md：更新受管區塊；其他內容不動'
    } elseif ($gemini.Trim()) {
      $plan += '  ~/.gemini/GEMINI.md：先備份成 GEMINI.md.pre-omnikit，在開頭加上受管區塊（原地改寫，硬連結到同一個檔案的其他名字會一起更新）'
    } else {
      $plan += '  ~/.gemini/GEMINI.md：建立，內容是底線與 profile'
    }
  }
  if ($Fresh) { $plan += '  ~/.claude/CLAUDE.md：受管區塊以外的舊規則先備份成 CLAUDE.md.pre-omnikit，再移除' }

  $skills = (Get-ChildItem -Directory (Join-Path $Repo 'engine\skills') | Where-Object { Test-Path (Join-Path $_.FullName 'SKILL.md') }).Name -join '、'
  if ($agents -contains 'claude-code') { $plan += "  skills：$skills 連到 ~/.claude/skills" }
  $shared = @($agents | Where-Object { $_ -in 'codex', 'antigravity' } | ForEach-Object { $AgentNames[$_] })
  if ($shared) { $plan += "  skills：$skills 複製到 ~/.agents/skills（給 $($shared -join '、')）" }
  $servers = [regex]::Matches((Get-FileText (Join-Path $Repo 'data\mcp\servers.yaml')), '(?m)^  ([A-Za-z0-9_-]+):\s*$') |
    ForEach-Object { $_.Groups[1].Value }
  $files = @{ 'claude-code' = '~/.claude.json'; 'codex' = '~/.codex/config.toml'; 'antigravity' = '~/.gemini/config/mcp_config.json' }
  if ($servers -and $agents) {
    $plan += "  MCP：$($servers -join '、') 寫進 $(($agents | ForEach-Object { $files[$_] }) -join '、')，不動其他設定"
  }
  $ssText = Get-FileText $SkillshareConfig
  if ($ssText -match '(?m)^\s*- name: rules-codex\s*$' -or $ssText -match '(?m)^  mcp: .*servers\.yaml' -or
      (Test-Path (Join-Path $env:APPDATA 'skillshare\skills\_omnikit'))) {
    $plan += '  不再使用 skillshare：改由 OmniKit 接手，拿掉 skillshare 設定裡 OmniKit 的部分（skillshare 本身不刪）'
  }

  $allow = @(Get-Content -Encoding UTF8 (Join-Path $Repo 'data\harness\claude-allow.txt') |
    ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
  if ($allow) { $plan += "~/.claude/settings.json：權限免問清單補上 $($allow -join '、')（只增不刪）" }
  $plan += '開新對話提醒：加進 ~/.claude/settings.json 與 ~/.codex/config.toml 的 Stop hook（Codex 要到 /hooks 信任才會跑）'
  if ((git -C $Repo config --get core.hooksPath) -ne '.githooks') {
    $plan += '這個 repo 改用 .githooks：commit 前掃金鑰、驗證名冊；改到規則、skills、MCP 等檔案時自動同步'
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
  $connected = try { @(([IO.File]::ReadAllText($AgentsFile) | ConvertFrom-Json).agents | ForEach-Object { $AgentNames[$_] }) } catch { @() }
  Write-Host ''
  Write-Host "OmniKit 已接上 $($connected -join '、')（profile：$name），開新的 session 才會生效："
  Write-Host "  - 問「OmniKit 規則版本與 profile 是什麼？」，應該回答 $version 與 $name"
  if ($name -eq 'default') {
    Write-Host '  - 建立自己的 profile：開新 session 說「幫我設定 OmniKit」（Claude Code 也可以輸入 /omnikit-setup，Codex 輸入 $omnikit-setup），回答幾題就好' -ForegroundColor Yellow
  } else {
    Write-Host '  - 重新設定 profile：開新 session 說「幫我設定 OmniKit」'
  }
  Write-Host '  - 換 profile：重跑 install.ps1 -ProfileName <名稱>，或 uv run engine/scripts/profiles.py --set <名稱>'
  Write-Host '  - 評估新工具：說「幫我評估」加上 GitHub 連結（Claude Code 也可以輸入 /omnikit-eval，Codex 輸入 $omnikit-eval）'
  Write-Host '  - 預設 plugin 不會自動安裝；安裝方式與其他說明見 README 的「裝好之後」'
}

if ($WhatIf) { Show-InstallPlan; return }

Install-Uv
Install-Gh
Install-Gitleaks
Sync-RepoConfig
Install-McpPackages
Connect-Agents
Grant-ClaudePermissions
Register-CodexHook
if ($Fresh) { Clear-OldClaudeRules }
Enable-GitHooks
Test-GitIdentity
Show-NextSteps
