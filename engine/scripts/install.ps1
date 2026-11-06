<#
OmniKit 安裝：把這台 Windows 電腦接上 OmniKit，可以重複執行。

接上的 agent 是偵測到的 Claude Code、Codex 與 Antigravity。全部由 OmniKit 自己的 Python 腳本接，
不經過 skillshare：公司電腦的防毒會擋下 skillshare（允許的通知要剛好盯著畫面才按得到）。

這台是同事版（預設）還是維護者版，見 engine/scripts/edition.py；兩版只差第 5 步的免問核准與第 6、7 步。

0. 安裝前檢查（engine/scripts/preflight.ps1）：git、連得到 GitHub、npm、PyPI、proxy、防毒、PowerShell 執行原則。
   任一項不通過就停下來、列出處理方式，什麼都不下載、不寫入。結果只印在這台，不上傳。
1. 安裝固定版本的 uv、gh 與 gitleaks（gitleaks 只有維護者版裝，給 pre-commit 用）：從 GitHub release
   下載 zip，比對寫死的 SHA256 後解壓；不改 PATH。這台已經有 uv 或 gh 就沿用。
2. fork 出來的 repo：把 data/omnikit.yaml 的 repo、owner、marketplace 改成 origin 指向的
   GitHub repo、profile 改回 default，並重新產生 marketplace 清單，避免跟原作者的 marketplace 撞名。
3. 依 data/mcp/packages.txt 全域安裝 MCP 用的 npm 套件（固定版本）。
4. 舊版把訪談產生的 profile 存在 repo 裡（data/profiles/<名稱>，有 answers.json、沒進版本控制）的話，
   交給 profiles.py --migrate 搬到 repo 外（%LOCALAPPDATA%\omnikit\profiles）；刪掉 repo 裡的舊檔前先問，
   不能互動時什麼都不改，只列出來（FR-38）。
   agents.py connect：
   - 規則 = 安全底線（data/rules/baseline.md）+ profile 的 AGENTS.md。訪談產生的 profile 在
     %LOCALAPPDATA%\omnikit\profiles\<名稱>（不在 repo 裡），default 與維護者手寫的在 data/profiles/<名稱>；同名時 repo 外的優先。
     Claude 在 ~/.claude/CLAUDE.md 用受管區塊 import；Codex 的 ~/.codex/AGENTS.md 與 Antigravity 的
     ~/.gemini/GEMINI.md 在開頭加受管區塊（原地改寫，硬連結不會斷），原本的規則留在區塊外照常生效，
     也先備份成 .pre-omnikit。沒指定也沒選過 profile 就用 default（下載、安裝前會先問）。
   - skills：engine/skills 連到 ~/.claude/skills；複製到 ~/.agents/skills 給 Codex 與 Antigravity。
   - MCP：data/mcp/servers.yaml 寫進三邊的設定，只動 OmniKit 管的欄位。agents.json 記每個 server 寫入時的
     雜湊；使用者改過的，或同名但不是 OmniKit 的，先停下來問，不覆蓋。
   - 舊版用 skillshare 接的，改由 OmniKit 接手，並拿掉 skillshare 設定裡 OmniKit 的部分（skillshare 本身不刪）。
5. 免問核准：Claude Code 的權限規則（data/harness/claude-allow.txt，只增不刪）與 Codex 的
   default_tools_approval_mode。維護者版照 data 寫入；同事版每個工具先問，本人同意了才寫入（預設否）。
   另外在 Claude Code 與 Codex 註冊開新對話提醒的 Stop hook（session_nudge.py）；
   Codex 要使用者在 /hooks 信任後才會執行。
6. git hook，只有維護者版：commit 前掃金鑰、驗證名冊；commit 或 pull 動到規則、skills、MCP 或權限規則時，
   自動同步。同事版不設 git hook，pull 不會改任何設定；要套用更新就重跑 install.ps1（先用 -WhatIf 預覽）。
7. 檢查 OmniKit repo 的 git 身分，只有維護者版。

每一步用 uv 跑 Python 腳本時，防毒短暫鎖住 uv 剛建好的暫存執行檔的話，等 3 秒重試一次（engine/scripts/uv-run.ps1，FR-34）。

這台原本沒有、由 OmniKit 裝上的工具、npm 套件與權限規則，會記在
%LOCALAPPDATA%\omnikit\install-record.json；接上了哪些 agent、管了哪些 skills 與 MCP，記在
%LOCALAPPDATA%\omnikit\agents.json。uninstall.ps1 只移除這些。

裝好之後，開新 session 說「幫我設定 OmniKit」，omnikit-setup 會用簡短訪談建立自己的 profile。

參數：
  -ProfileName <名稱>  用這個 profile 的個人規則，並記下來；之後重跑不用再指定。先找 repo 外的
                       %LOCALAPPDATA%\omnikit\profiles\<名稱>（訪談產生的），再找 data/profiles/<名稱>。
  -Edition <版本>      colleague（同事版）或 maintainer（維護者版），記下來；之後重跑不用再指定。
                       沒指定也沒記過：分版之前就裝過的電腦是維護者版，其他都是同事版。
  -Fresh               這台第一次接上 OmniKit 時使用：把 ~/.claude/CLAUDE.md 受管區塊以外的舊規則
                       備份後移除，避免新舊規則同時生效。
  -WhatIf              預覽：依這台目前的狀態列出會改動的地方，什麼都不做（不下載、不寫檔）；也會跑安裝前檢查。
  -SkipCheck <名稱>    安裝前檢查要略過的項目（已經自己處理好，例如防毒已請 IT 放行：-SkipCheck antivirus）。
  -SelfTest            自我測試：在暫存資料夾與暫存 git repo 測版本判斷、git hook 設定與 profile 的位置，
                       以及 uv 被防毒鎖住時的重試（用假的鎖檔），不動這台的設定。

用法（Windows PowerShell 5.1 或 PowerShell 7）：
  powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\install.ps1 [-ProfileName <名稱>] [-Edition colleague|maintainer] [-Fresh] [-WhatIf]
#>
param([string]$ProfileName, [ValidateSet('colleague', 'maintainer')][string]$Edition, [switch]$Fresh, [switch]$WhatIf,
  [switch]$SelfTest, [string[]]$SkipCheck = @())

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
$EditionPy = Join-Path $Repo 'engine\scripts\edition.py'
$PreflightPs1 = Join-Path $Repo 'engine\scripts\preflight.ps1'
$EditionNames = @{ 'colleague' = '同事版'; 'maintainer' = '維護者版' }
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

# Invoke-UvRun：跑 uv，防毒短暫鎖住 uv 的暫存執行檔時等一下重試一次（FR-34）
. (Join-Path $PSScriptRoot 'uv-run.ps1')

# 優先用 PATH 上的 uv，沒有就用 Install-Uv 裝的那一份。只找執行檔：Invoke-UvRun 直接啟動它，不經過 PowerShell
function Get-Uv {
  $onPath = (Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
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
  $r = Invoke-UvRun (Get-Uv) @('run', '--quiet', (Join-Path $Repo 'engine\scripts\build.py'), '--marketplace-only') -Capture
  if ($r.Code -ne 0) { throw "build.py --marketplace-only 失敗（exit $($r.Code)）" }
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

# 這台是同事版還是維護者版（engine/scripts/edition.py）：-Edition 指定的記下來；
# 沒指定就照記錄或判斷，也記下來，之後重跑結果一樣
function Resolve-Edition($wanted) {
  # 整個包在 @() 裡：只有一個元素時 if 會回傳字串，不是陣列
  $editionArgs = @(if ($wanted) { '--set', $wanted } else { '--save' })
  # 只接 ASCII 的值（maintainer 或 colleague）
  $r = Invoke-UvRun (Get-Uv) (@('run', '--quiet', $EditionPy) + $editionArgs + '--show') -Capture
  $value = $r.Output.Trim()
  if ($r.Code -ne 0 -or $value -notin $EditionNames.Keys) { throw "edition.py 失敗（exit $($r.Code)）" }
  Write-Host "OmniKit 版本：$($EditionNames[$value])"
  return $value
}

# -WhatIf 用：只判斷不記錄；還沒有 uv 的電腦一定還沒裝過，就是同事版
function Get-EditionPreview($wanted) {
  if ($wanted) { return $wanted }
  if ((Get-Command uv -ErrorAction SilentlyContinue) -or (Test-Path $UvExe)) {
    $value = (Invoke-UvRun (Get-Uv) @('run', '--quiet', $EditionPy, '--show') -Capture).Output.Trim()
    if ($value -in $EditionNames.Keys) { return $value }
  }
  return 'colleague'
}

# 同事版：免問核准每個工具先問，本人同意了才寫入（預設否）；不能互動時一個都不寫
function Request-AutoApprove {
  $r = Invoke-UvRun (Get-Uv) @('run', '--quiet', $AgentsPy, 'approvals', '--ask')
  if ($r.Code -ne 0) { throw "agents.py approvals 失敗（exit $($r.Code)）" }
}

# profile 的資料夾：跟 profiles.py 的 folder 一樣，先找 repo 外的（訪談產生的），再找 repo 裡的；都沒有回 $null
function Get-ProfileDir($name) {
  foreach ($dir in @((Join-Path $env:LOCALAPPDATA "omnikit\profiles\$name"), (Join-Path $Repo "data\profiles\$name"))) {
    if (Test-Path -LiteralPath (Join-Path $dir 'AGENTS.md')) { return $dir }
  }
  return $null
}

# -ProfileName 有問題的原因；沒問題回 $null。安裝一開始就檢查，免得下載、寫入到一半才在接上 agent 時失敗
function Test-ProfileName($name) {
  if (-not $name) { return $null }
  if ($name -cnotmatch '^[a-z0-9]+(-[a-z0-9]+)*$') { return "profile 名稱只能用小寫英數與 -：$name" }
  if (-not (Get-ProfileDir $name)) {
    return "找不到 profile「$name」（$(Join-Path $env:LOCALAPPDATA "omnikit\profiles\$name") 或 data/profiles/$name，要有 AGENTS.md）"
  }
  return $null
}

# 舊版存在 repo 裡、由訪談產生的 profile：跟 profiles.py 的 legacy 一樣，有 answers.json、沒進版本控制的才算
function Get-LegacyProfiles {
  $root = Join-Path $Repo 'data\profiles'
  if (-not (Test-Path -LiteralPath $root)) { return @() }
  # git 印出的是相對於 repo 的路徑；不轉向 stderr（PowerShell 5.1 在 Stop 模式下會當成錯誤丟出）
  $tracked = @(git -C $Repo ls-files -- data/profiles | ForEach-Object { ($_ -split '/')[2] } | Select-Object -Unique)
  return @(Get-ChildItem -LiteralPath $root -Directory | Where-Object {
      $_.Name -cmatch '^[a-z0-9]+(-[a-z0-9]+)*$' -and $_.Name -notin $tracked -and
      (Test-Path -LiteralPath (Join-Path $_.FullName 'answers.json'))
    } | ForEach-Object { $_.Name })
}

# 舊版存在 repo 裡的 profile 搬到 repo 外（FR-38）。能互動時 profiles.py 會先問，刪掉 repo 裡的舊檔前一定要同意；
# 不能互動時什麼都不改，只列出來。沒有要搬的就不跑
function Move-LegacyProfiles {
  if (-not @(Get-LegacyProfiles).Count) { return }
  $r = Invoke-UvRun (Get-Uv) @('run', '--quiet', $ProfilesPy, '--migrate')
  if ($r.Code -ne 0) { throw "profiles.py --migrate 失敗（exit $($r.Code)）" }
}

# 規則、skills、MCP 都交給 agents.py（維護者版的 git hook 也用它同步）。
# MCP 被使用者改過、或同名但不是 OmniKit 的，--ask 會逐一問；不能互動時列出來並停下，什麼都不寫
function Connect-Agents {
  $profileArgs = @(if ($ProfileName) { '--profile', $ProfileName })
  $r = Invoke-UvRun (Get-Uv) (@('run', '--quiet', $AgentsPy, 'connect') + $profileArgs + '--ask')
  if ($r.Code -ne 0) { throw "agents.py connect 失敗（exit $($r.Code)）" }
}

# Claude Code 免問的權限規則；JSON 交給 Python 改，PowerShell 5.1 的 ConvertTo-Json 會改掉原本的格式
function Grant-ClaudePermissions {
  $r = Invoke-UvRun (Get-Uv) @('run', '--quiet', (Join-Path $Repo 'engine\scripts\claude_allow.py'))
  if ($r.Code -ne 0) { throw "claude_allow.py 失敗（exit $($r.Code)）" }
}

# Codex 的開新對話提醒 hook；TOML 交給 Python 改，寫入前會驗證沒動到其他設定。
# 只是提醒，失敗時警告就好，不擋後面的步驟
function Register-CodexHook {
  $r = Invoke-UvRun (Get-Uv) @('run', '--quiet', (Join-Path $Repo 'engine\scripts\codex_hooks.py'))
  if ($r.Code -ne 0) { Write-Warning "codex_hooks.py 失敗（exit $($r.Code)），Codex 的開新對話提醒沒有註冊" }
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

# 維護者版：commit 前掃金鑰、驗證名冊，commit 或 pull 後自動同步。
# 同事版不設 git hook，pull 不會改任何設定；以前設過的拿掉
function Set-GitHooks($edition) {
  if ($edition -eq 'maintainer') {
    git -C $Repo config core.hooksPath .githooks
  } elseif ((git -C $Repo config --get core.hooksPath) -eq '.githooks') {
    git -C $Repo config --unset core.hooksPath
    Write-Host '同事版：這個 repo 不再使用 .githooks，pull 不會自動改設定'
  }
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
  $edition = Get-EditionPreview $Edition
  $plan = @()
  if ($edition -eq 'maintainer') {
    $plan += '版本：維護者版（commit 或 pull 後 git hook 自動同步；免問核准照 data 寫入）'
  } else {
    $plan += '版本：同事版（不設 git hook，pull 不會自動改設定；免問核准每個工具先問你）'
  }
  $tools = @(
    @{ Name = 'uv'; Version = $UvVersion; Path = $UvExe; Command = 'uv' },
    @{ Name = 'gh'; Version = $GhVersion; Path = $GhExe; Command = 'gh' }
  )
  if ($edition -eq 'maintainer') {
    $tools += @{ Name = 'gitleaks'; Version = $GitleaksVersion; Path = $GitleaksExe; Command = $null }
  }
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
  $legacyProfiles = @(Get-LegacyProfiles)
  if ($legacyProfiles) {
    $dest = Join-Path $env:LOCALAPPDATA 'omnikit\profiles'
    $plan += "  舊版存在 repo 裡的 profile（$($legacyProfiles -join '、')）：搬到 $dest（不會被 commit）；刪掉 repo 裡的舊檔前先問你，不能互動時不搬"
  }
  $stateFile = Join-Path $env:LOCALAPPDATA 'omnikit\profile.json'
  $chosen = if (Test-Path -LiteralPath $stateFile) { try { ([IO.File]::ReadAllText($stateFile) | ConvertFrom-Json).profile } catch { $null } }
  $name = if ($ProfileName) { $ProfileName } elseif ($chosen) { $chosen } else { 'default' }
  $note = if ($ProfileName -or $chosen) { '' } else { '（還沒選過，用預設：下載、安裝前會先問）' }
  $profileDir = Get-ProfileDir $name
  $where = if (-not $profileDir) { '' } elseif ($profileDir.StartsWith($Repo)) { "，data/profiles/$name" } else { "，$profileDir" }
  $plan += "  規則：安全底線 + profile「$name」$note$where"
  if (-not $profileDir) {
    $plan += "  找不到 profile「$name」（$(Join-Path $env:LOCALAPPDATA "omnikit\profiles\$name") 或 data/profiles/$name，要有 AGENTS.md），安裝會在這一步失敗"
  }
  if ($agents -contains 'claude-code') {
    $verb = if ((Get-FileText $ClaudeMd) -match $BlockPattern) { '更新' } else { '在開頭加上' }
    $plan += "  ~/.claude/CLAUDE.md：$($verb)受管區塊，import 底線與 profile；其他內容不動"
  }
  if ($agents -contains 'codex') {
    $legacy = (Get-FileText $SkillshareConfig) -match '(?m)^\s*- name: rules-codex\s*$'
    $codex = Get-FileText $CodexMd
    if ($codex -match $BlockPattern) {
      $plan += '  ~/.codex/AGENTS.md：更新受管區塊；其他內容不動'
    } elseif ($codex.TrimStart().StartsWith($OursHeader) -or ($legacy -and $codex.Trim())) {
      $plan += '  ~/.codex/AGENTS.md：舊版整份都是 OmniKit 產生的，換成只有受管區塊（規則內容一樣）'
    } elseif ($codex.Trim()) {
      $plan += '  ~/.codex/AGENTS.md：先備份成 AGENTS.md.pre-omnikit，在開頭加上受管區塊；原本的規則留在區塊外，照常生效'
    } else {
      $plan += '  ~/.codex/AGENTS.md：建立，內容是底線與 profile 的受管區塊'
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

  # 跟 profiles.py 的 OPTIONAL_SKILLS 一樣：訪談第 5 題答「不要」（evaluate_tools 是 false）就不裝 omnikit-eval
  $answersFile = if ($profileDir) { Join-Path $profileDir 'answers.json' } else { '' }
  $skip = @()
  if ($answersFile -and (Test-Path -LiteralPath $answersFile)) {
    try { if ((Get-FileText $answersFile | ConvertFrom-Json).evaluate_tools -eq $false) { $skip = @('omnikit-eval') } } catch { }
  }
  $skills = (Get-ChildItem -Directory (Join-Path $Repo 'engine\skills') |
    Where-Object { (Test-Path (Join-Path $_.FullName 'SKILL.md')) -and $_.Name -notin $skip }).Name -join '、'
  if ($skip) { $plan += "  skills：profile「$name」選了不評估新工具，不裝 $($skip -join '、')" }
  if ($agents -contains 'claude-code') { $plan += "  skills：$skills 連到 ~/.claude/skills" }
  $shared = @($agents | Where-Object { $_ -in 'codex', 'antigravity' } | ForEach-Object { $AgentNames[$_] })
  if ($shared) { $plan += "  skills：$skills 複製到 ~/.agents/skills（給 $($shared -join '、')）" }
  $servers = [regex]::Matches((Get-FileText (Join-Path $Repo 'data\mcp\servers.yaml')), '(?m)^  ([A-Za-z0-9_-]+):\s*$') |
    ForEach-Object { $_.Groups[1].Value }
  $files = @{ 'claude-code' = '~/.claude.json'; 'codex' = '~/.codex/config.toml'; 'antigravity' = '~/.gemini/config/mcp_config.json' }
  if ($servers -and $agents) {
    $plan += "  MCP：$($servers -join '、') 寫進 $(($agents | ForEach-Object { $files[$_] }) -join '、')，只動 OmniKit 管的欄位；被你改過或同名但不是 OmniKit 的，先問你"
  }
  $ssText = Get-FileText $SkillshareConfig
  if ($ssText -match '(?m)^\s*- name: rules-codex\s*$' -or $ssText -match '(?m)^  mcp: .*servers\.yaml' -or
      (Test-Path (Join-Path $env:APPDATA 'skillshare\skills\_omnikit'))) {
    $plan += '  不再使用 skillshare：改由 OmniKit 接手，拿掉 skillshare 設定裡 OmniKit 的部分（skillshare 本身不刪）'
  }

  $allow = @(Get-Content -Encoding UTF8 (Join-Path $Repo 'data\harness\claude-allow.txt') |
    ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
  if ($edition -eq 'maintainer') {
    if ($allow) { $plan += "~/.claude/settings.json：權限免問清單補上 $($allow -join '、')（只增不刪）；Codex 照 servers.yaml 設 default_tools_approval_mode" }
  } elseif ($allow) {
    # 跟 edition.py 的 tool_of 一樣：mcp__<server>（__<工具>）算在那個 server
    $approveTools = @($allow | ForEach-Object { $_ -replace '^mcp__(.+?)(__.+)?$', '$1' } | Select-Object -Unique)
    $plan += "免問核准（$($approveTools -join '、')）：安裝時逐一問你，同意了才寫進 ~/.claude/settings.json 與 ~/.codex/config.toml（預設否）"
  }
  $plan += '開新對話提醒：加進 ~/.claude/settings.json 與 ~/.codex/config.toml 的 Stop hook（Codex 要到 /hooks 信任才會跑）'
  $hooksOn = (git -C $Repo config --get core.hooksPath) -eq '.githooks'
  if ($edition -eq 'maintainer' -and -not $hooksOn) {
    $plan += '這個 repo 改用 .githooks：commit 前掃金鑰、驗證名冊；改到規則、skills、MCP 等檔案時自動同步'
  } elseif ($edition -ne 'maintainer' -and $hooksOn) {
    $plan += '這個 repo 不再使用 .githooks：同事版不設 git hook，pull 不會自動改設定'
  } elseif ($edition -ne 'maintainer') {
    $plan += '不設 git hook：pull 不會自動改設定；要套用更新就重跑 install.ps1（先用 -WhatIf 預覽）'
  }

  Write-Host '這是預覽，什麼都沒改。照這台目前的狀態，install.ps1 會：'
  # 兩個空白開頭的是上一項的細節，縮排顯示
  $plan | ForEach-Object { if ($_.StartsWith('  ')) { Write-Host "      $($_.Trim())" } else { Write-Host "  - $_" } }
  Write-Host ''
  Write-Host '拿掉 -WhatIf 再執行就會照做；每一項的說明見 README 的「安裝會改動哪些地方」。'
}

# 安裝完畫面上不會多出東西，告訴使用者怎麼確認接上了、接下來怎麼用
function Show-NextSteps($edition) {
  $text = [IO.File]::ReadAllText((Join-Path $Repo 'data\rules\baseline.md'), [Text.Encoding]::UTF8)
  $version = if ($text -match '規則版本：(\S+)') { $Matches[1] } else { 'data/rules/baseline.md 開頭的版本' }
  # 只接 ASCII 的值：profile 名稱只能用小寫英數與 -
  $name = (Invoke-UvRun (Get-Uv) @('run', '--quiet', $ProfilesPy, '--show') -Capture).Output.Trim()
  $record = try { [IO.File]::ReadAllText($AgentsFile) | ConvertFrom-Json } catch { $null }
  $connected = @($record.agents | Where-Object { $_ } | ForEach-Object { $AgentNames[$_] })
  $hasEval = @($record.skills.PSObject.Properties.Value | ForEach-Object { $_ }) -contains 'omnikit-eval'
  Write-Host ''
  Write-Host "OmniKit 已接上 $($connected -join '、')（profile：$name），開新的 session 才會生效："
  Write-Host "  - 問「OmniKit 規則版本與 profile 是什麼？」，應該回答 $version 與 $name"
  if ($name -eq 'default') {
    Write-Host '  - 建立自己的 profile：開新 session 說「幫我設定 OmniKit」（Claude Code 也可以輸入 /omnikit-setup，Codex 輸入 $omnikit-setup），回答幾題就好' -ForegroundColor Yellow
  } else {
    Write-Host '  - 重新設定 profile：開新 session 說「幫我設定 OmniKit」'
  }
  Write-Host '  - 換 profile：重跑 install.ps1 -ProfileName <名稱>，或 uv run engine/scripts/profiles.py --set <名稱>'
  if ($edition -ne 'maintainer') {
    Write-Host '  - 這台是同事版：pull 不會自動改設定；要套用更新，先跑 install.ps1 -WhatIf 預覽，再跑 install.ps1'
    Write-Host '  - 免問核准：uv run engine/scripts/agents.py approvals 查看；--grant <名稱> 同意、--revoke <名稱> 撤回'
  }
  if ($hasEval) {
    Write-Host '  - 評估新工具：說「幫我評估」加上 GitHub 連結（Claude Code 也可以輸入 /omnikit-eval，Codex 輸入 $omnikit-eval）'
  }
  Write-Host '  - 預設 plugin 不會自動安裝；安裝方式與其他說明見 README 的「裝好之後」'
}

# -SelfTest：%LOCALAPPDATA% 換成暫存資料夾、repo 換成暫存 git repo，測版本判斷與 git hook 設定
function Invoke-SelfTest {
  $script:failures = 0
  function Check($label, $ok) {
    if ($ok) { Write-Host "通過：$label" } else { Write-Host "失敗：$label"; $script:failures++ }
  }
  # 名稱短一點：暫存資料夾本身很深時（CI 故意用長路徑），git 物件的路徑才不會超過 260 字元
  $tmp = Join-Path ([IO.Path]::GetTempPath()) ('okst-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
  New-Item -ItemType Directory -Path $tmp | Out-Null
  $realLocal, $realRepo, $realUvCache = $env:LOCALAPPDATA, $script:Repo, $env:UV_CACHE_DIR
  # uv 的快取預設在 %LOCALAPPDATA%，換掉之前先指回原本的，免得重新下載
  if (-not $env:UV_CACHE_DIR) { $env:UV_CACHE_DIR = Join-Path $realLocal 'uv\cache' }
  try {
    $env:LOCALAPPDATA = Join-Path $tmp 'local'
    $editionFile = Join-Path $env:LOCALAPPDATA 'omnikit\edition.json'
    Check 'Get-EditionPreview：沒有記錄是同事版，而且不寫檔' ((Get-EditionPreview '') -eq 'colleague' -and -not (Test-Path $editionFile))
    Check 'Resolve-Edition：沒指定就照判斷（同事版）並記下來' ((Resolve-Edition '') -eq 'colleague' -and (Get-FileText $editionFile) -match '"colleague"')
    Check 'Resolve-Edition：-Edition maintainer 記成維護者版' ((Resolve-Edition 'maintainer') -eq 'maintainer' -and (Get-FileText $editionFile) -match '"maintainer"')
    Check 'Resolve-Edition：之後沒指定就沿用記錄' ((Resolve-Edition '') -eq 'maintainer')
    Check 'Get-EditionPreview：照記錄' ((Get-EditionPreview '') -eq 'maintainer')
    Check 'Get-EditionPreview：有指定就用指定的' ((Get-EditionPreview 'colleague') -eq 'colleague')

    $script:Repo = Join-Path $tmp 'repo'
    git init --quiet $script:Repo
    git -C $script:Repo config core.hooksPath .githooks
    Set-GitHooks 'colleague'
    Check 'Set-GitHooks colleague：拿掉以前設的 .githooks，pull 不會自動同步' (-not (git -C $script:Repo config --get core.hooksPath))
    Set-GitHooks 'colleague'
    Check 'Set-GitHooks colleague：本來就沒設，不出錯' (-not (git -C $script:Repo config --get core.hooksPath))
    Set-GitHooks 'maintainer'
    Check 'Set-GitHooks maintainer：設成 .githooks' ((git -C $script:Repo config --get core.hooksPath) -eq '.githooks')

    # profile 的位置（FR-38）：訪談產生的在 repo 外，同名時優先；舊版存在 repo 裡、沒進版本控制的要搬
    $utf8 = New-Object Text.UTF8Encoding($false)
    $put = { param($path, $text) New-Item -ItemType Directory -Force -Path (Split-Path $path) | Out-Null; [IO.File]::WriteAllText($path, $text, $utf8) }
    $inRepo = Join-Path $script:Repo 'data\profiles'
    $local = Join-Path $env:LOCALAPPDATA 'omnikit\profiles'
    & $put (Join-Path $inRepo 'default\AGENTS.md') "# default`n"
    & $put (Join-Path $inRepo 'ryan\AGENTS.md') "# 維護者 commit 的`n"
    & $put (Join-Path $inRepo 'ryan\answers.json') '{}'
    & $put (Join-Path $inRepo 'alice\AGENTS.md') "# 舊版訪談存在 repo 裡`n"
    & $put (Join-Path $inRepo 'alice\answers.json') '{"evaluate_tools": false}'
    & $put (Join-Path $inRepo 'bob\AGENTS.md') "# 手寫的`n"
    & $put (Join-Path $local 'ryan\AGENTS.md') "# repo 外的同名 profile`n"
    git -C $script:Repo -c core.autocrlf=false -c core.longpaths=true add data/profiles/default data/profiles/ryan
    Check 'Get-LegacyProfiles：有 answers.json、沒進版本控制的才算（手寫的與 commit 過的不算）' ((@(Get-LegacyProfiles) -join ',') -eq 'alice')
    Check 'Get-ProfileDir：同名時 repo 外的優先' ((Get-ProfileDir 'ryan') -eq (Join-Path $local 'ryan'))
    Check 'Get-ProfileDir：repo 外沒有就用 repo 裡的' ((Get-ProfileDir 'alice') -eq (Join-Path $inRepo 'alice'))
    Check 'Get-ProfileDir：都沒有回 $null' ($null -eq (Get-ProfileDir 'nope'))
    Check 'Test-ProfileName：沒指定、repo 外或 repo 裡找得到的都沒問題' ($null -eq (Test-ProfileName '') -and
      $null -eq (Test-ProfileName 'ryan') -and $null -eq (Test-ProfileName 'alice'))
    Check 'Test-ProfileName：格式不對（例如誤把 -SelfTest 當成名稱）或找不到，安裝一開始就停' (
      (Test-ProfileName '-SelfTest') -match '小寫英數' -and (Test-ProfileName 'Bad_Name') -match '小寫英數' -and
      (Test-ProfileName 'nope') -match '找不到 profile「nope」')

    # 防毒短暫鎖住 uv 的暫存執行檔（FR-34）：用真的 uv 跑一支假的腳本，照計數檔決定第幾次要印出
    # uv 被鎖住時的訊息並失敗。這裡在 Stop 模式下跑，stderr 有輸出也不能丟出錯誤
    $fake = Join-Path $tmp 'fake_lock.py'
    [IO.File]::WriteAllText($fake, @'
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""install.ps1 -SelfTest 用：照計數檔假裝 uv 的暫存執行檔被防毒鎖住，或是別的失敗。stdout 只印 ASCII。"""
import json
import sys
from pathlib import Path

counter, mode = Path(sys.argv[1]), sys.argv[2]
runs = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(runs))
if mode == "locked" or (mode == "locked-once" and runs == 1):
    sys.stderr.buffer.write(rb"error: Failed to update Windows PE resources: C:\Temp\uv-trampoline-selftest.exe" + b"\n")
    sys.stderr.buffer.write("  Caused by: 系統無法開啟指定的裝置或檔案。 (os error -2147024786)\n".encode())
    sys.exit(2)
if mode == "other":
    sys.stderr.buffer.write("找不到 profile「nope」（自我測試）\n".encode())
    sys.exit(1)
print(json.dumps(sys.argv[3:]))
'@, $utf8)
    $UvRetrySeconds = 0  # 只在這個函式裡：自我測試不用真的等
    $runFake = { param($mode, [string[]]$extra = @())
      $counter = Join-Path $tmp "fake-$mode.txt"
      $r = Invoke-UvRun (Get-Uv) (@('run', '--quiet', $fake, $counter, $mode) + $extra) -Capture
      $runs = if (Test-Path -LiteralPath $counter) { [int][IO.File]::ReadAllText($counter) } else { 0 }
      $r | Add-Member -NotePropertyName Runs -NotePropertyValue $runs -PassThru
    }
    $r = & $runFake 'locked-once'
    Check 'uv 的暫存執行檔被防毒鎖住一次：等一下重試，第二次就成功' ($r.Code -eq 0 -and $r.Retried -and $r.Runs -eq 2)
    $r = & $runFake 'locked'
    Check 'uv 一直被鎖住：只重試一次，結束碼照實回傳（呼叫的地方照舊丟出）' ($r.Code -eq 2 -and $r.Retried -and $r.Runs -eq 2)
    $r = & $runFake 'other'
    Check '其他失敗不重試；Stop 模式下不丟出，中文的錯誤訊息照原樣（不會變成 cp950 亂碼）' ($r.Code -eq 1 -and -not $r.Retried -and
      $r.Runs -eq 1 -and $r.Error -eq '找不到 profile「nope」（自我測試）')
    $weird = @('有 空白', 'say "hi"', 'C:\結尾是反斜線\', '', 'x\"y')
    $r = & $runFake 'ok' $weird
    # PowerShell 5.1 的 ConvertFrom-Json 把整個陣列當成一個物件輸出，所以不包 @()，直接 -join
    Check 'Invoke-UvRun：參數有空白、引號、中文、結尾的反斜線或是空字串，都原樣傳給腳本' ($r.Code -eq 0 -and -not $r.Retried -and
      (($r.Output | ConvertFrom-Json) -join '|') -eq ($weird -join '|'))
    $cp950 = [Text.Encoding]::GetEncoding(950)
    $mixed = $utf8.GetBytes("UTF-8 的中文`r`n") + $cp950.GetBytes("cp950 的中文`n")
    Check 'stderr 逐行解碼：UTF-8 照用，不是 UTF-8 的才用主控台字碼頁（cp950）' (
      (ConvertFrom-UvBytes $mixed $cp950) -eq "UTF-8 的中文`ncp950 的中文")
  } finally {
    $env:LOCALAPPDATA, $script:Repo, $env:UV_CACHE_DIR = $realLocal, $realRepo, $realUvCache
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
  }
  Write-Host ''
  Write-Host $(if ($script:failures) { "$($script:failures) 項失敗" } else { '全部通過' })
  return $script:failures
}

if ($SelfTest) { exit (Invoke-SelfTest) }

# -ProfileName 不對就什麼都不做（-WhatIf 照樣列在預覽裡）
$ProfileProblem = Test-ProfileName $ProfileName
if ($ProfileProblem -and -not $WhatIf) {
  Write-Host "$ProfileProblem。什麼都沒有下載或寫入。"
  exit 1
}

# 安裝前檢查（FR-35）：任一項不通過就什麼都不下載、不寫入
& $PreflightPs1 -Skip $SkipCheck
$PreflightOk = ($LASTEXITCODE -eq 0)
Write-Host ''
if ($WhatIf) {
  if (-not $PreflightOk) { Write-Host '注意：安裝前檢查沒通過，照上面的處理方式處理好之前，實際安裝會停在這一步。'; Write-Host '' }
  Show-InstallPlan
  return
}
if (-not $PreflightOk) {
  Write-Host '安裝前檢查沒通過，什麼都沒有下載或寫入。照上面的處理方式處理好再重跑。'
  exit 1
}

Install-Uv
Install-Gh
$CurrentEdition = Resolve-Edition $Edition
if ($CurrentEdition -eq 'maintainer') { Install-Gitleaks }
Sync-RepoConfig
Install-McpPackages
if ($CurrentEdition -ne 'maintainer') { Request-AutoApprove }
Move-LegacyProfiles
Connect-Agents
Grant-ClaudePermissions
Register-CodexHook
if ($Fresh) { Clear-OldClaudeRules }
Set-GitHooks $CurrentEdition
if ($CurrentEdition -eq 'maintainer') { Test-GitIdentity }
Show-NextSteps $CurrentEdition
