<#
OmniKit 安裝：把這台 Windows 電腦接上 OmniKit，可以重複執行。

接上的 agent 是偵測到的 Claude Code、Codex 與 Antigravity。全部由 OmniKit 自己的 Python 腳本接，
不經過 skillshare：公司電腦的防毒會擋下 skillshare（允許的通知要剛好盯著畫面才按得到）。

預設為標準安裝（鎖定最新穩定發行 tag、乾淨參照副本、不設 git hook）；開發 OmniKit 本身或 fork 自建名冊時請加 -Dev。

0. 安裝前檢查（engine/scripts/preflight.ps1）：git、連得到 GitHub、npm、PyPI、proxy、防毒、PowerShell 執行原則。
   任一項不通過就停下來、列出處理方式，什麼都不下載、不寫入。結果只印在這台，不上傳。
1. 安裝固定版本的 uv、gh 與 gitleaks：從 GitHub release
   下載 zip，比對寫死的 SHA256 後解壓；不改 PATH。這台已經有 uv 或 gh 就沿用。
2. 開發模式（-Dev）下若為 fork 出來的 repo：把 data/omnikit.yaml 的 repo、owner、marketplace 改成 origin 指向的
   GitHub repo、profile 改回 default，並重新產生 marketplace 清單，避免跟原作者的 marketplace 撞名。
3. 依 data/mcp/packages.txt 全域安裝 MCP 用的 npm 套件（固定版本）。
4. 舊版把訪談產生的 profile 存在 repo 裡（data/profiles/<名稱>，有 answers.json、沒進版本控制）的話，
   交給 profiles.py --migrate 搬到 repo 外（~/.omnikit/profiles）；刪掉 repo 裡的舊檔前先問，
   不能互動時什麼都不改，只列出來（FR-38）。
   sync.py connect：
   - 規則 = 安全底線（data/rules/baseline.md）+ 分派共用層（data/rules/dispatch.md）+ profile 的 AGENTS.md。訪談產生的 profile 在
     ~/.omnikit/profiles/<名稱>（不在 repo 裡），default 與隨 repo 維護的在 data/profiles/<名稱>；同名時 repo 外的優先。
     Claude 在 ~/.claude/CLAUDE.md 用受管區塊 import；Codex 的 ~/.codex/AGENTS.md 與 Antigravity 的
     ~/.gemini/AGENTS.md（共用）、GEMINI.md（個人）在開頭加受管區塊（原地改寫，硬連結不會斷），原本的規則留在區塊外照常生效，
     也先備份成 .pre-omnikit。沒指定也沒選過 profile 就用 default（下載、安裝前會先問）。
     其他設定目錄（engine/scripts/homes.py 找：CLAUDE_CONFIG_DIR、CODEX_HOME、T3 Code 每個實例的 homePath、
     明確列舉於 config.json 的額外目錄）：Claude 的 CLAUDE.md、Codex 的 AGENTS.md 也放同一個區塊，
     MCP 也寫進去，Claude 與 Codex 的 skills 也連進去。agent 只讀自己設定目錄的規則，不放就讀不到。
     Claude 的其他設定目錄也同步你自己裝在 ~/.claude 的 skill（資料夾連結）與啟用中的 plugin
     （claude plugin install，CLAUDE_CONFIG_DIR 指過去）；之後新裝的，重跑 sync.py sync 就補上。
     安裝之後才新增的帳號：開新對話時 home_watch.py 發現，就在背景接上（也可以跑 sync.py sync）。
     T3 Code 的 Antigravity 實例：T3 會原生同步 ~/.gemini 的規則與 skills.json；OmniKit 會在 ~/.gemini 與各 T3 實例
     放置 config/plugins/omnikit/ 薄 plugin（護欄與 MCP），並自動清理舊版停用的 ACP 轉接程式（~/.omnikit/acp/）。
   - skills：Claude Code（~/.claude/skills）與 Codex（~/.codex/skills）以 Directory Junction 連結至
     ~/.omnikit/current/engine/skills（-Dev 開發模式直連本地開發倉庫，零檔案複製與零雜湊帳本）；Antigravity 透過
     ~/.gemini/config/skills.json 原生參照實體 skills 路徑（T3 自動同步至全部實例），並自動清理舊版複製品。
   - MCP 與護欄 hooks：無帳本對帳 data/mcp/servers.yaml。Claude Code 透過本地薄 plugin（~/.omnikit/claude-marketplace
     內的 omnikit@omnikit-local）掛載 hooks 與 MCP（不動頂層 ~/.claude.json，找不到 claude CLI 時才退回 settings.json hooks 備案）；
     Codex 透過 codex mcp CLI 與 ~/.codex/config.toml 管理；Antigravity 於 ~/.gemini 與各 T3 實例放置
     config/plugins/omnikit/ 三檔薄宣告（不動頂層 mcp_config.json，保留 T3 自動標題生成）。
   - 舊版用 skillshare 接的，改由 OmniKit 接手，並拿掉 skillshare 設定裡 OmniKit 的部分（skillshare 本身不刪）。
5. 免問核准與護欄 hooks：Claude Code 的權限規則（data/harness/claude-allow.txt 現行＋墓碑清單，只增不刪使用者自訂規則）
   與 Codex 的 default_tools_approval_mode 統一由本人同意紀錄（consent.json）或本機控制面板工作台開關決定（預設否）。
   護欄與提醒 hooks（確定性護欄 harness_hooks.py、開新對話提醒 session_nudge.py、說做不到查證 claim_check.py、
   完工宣稱檢查 done_check.py（預設只記錄）、設定目錄檢查 home_watch.py、T3 MCP 斷線防護 t3_watch.py）：Claude 經由薄 plugin 掛載並寫入 statusLine；
   Codex 寫進 config.toml（需在 /hooks 信任才會執行）；Antigravity 經由薄 plugin hooks.json 掛載確定性護欄與完工宣稱檢查。
6. git hook（僅 -Dev 開發模式）：commit 前掃金鑰、驗證名冊；commit 或 pull 動到規則、skills、MCP 或權限規則時，
   自動同步。標準安裝不設 git hook，pull 不會改任何設定；要套用更新就重跑 install.ps1（先用 -WhatIf 預覽）。
7. 檢查 OmniKit repo 的 git 身分（僅 -Dev 開發模式）。

每一步用 uv 跑 Python 腳本時，防毒短暫鎖住 uv 剛建好的暫存執行檔的話，等 3 秒重試一次（engine/scripts/uv-run.ps1，FR-34）。

這台原本沒有、由 OmniKit 裝上的工具、npm 套件與權限規則，會記在
~/.omnikit/install-record.json；接上了哪些 agent、repo 路徑與設定，記在
~/.omnikit/config.json（無雜湊帳本，期望狀態由 repo manifest 直接計算）。uninstall.ps1 依安裝紀錄與無狀態對帳還原。
狀態放家目錄的 ~/.omnikit，不放 %LOCALAPPDATA%：從 Claude 桌面版這類 Microsoft Store（MSIX）封裝的 app 裡跑時，
AppData 底下新建的檔會被轉存到那個 app 自己的位置，終端機、T3 Code、Codex 看不到，同一台就有兩份狀態。
舊版放在 %LOCALAPPDATA%\omnikit 的（以及被轉存的副本），uv 裝好後第一步就合併進 ~/.omnikit（engine/scripts/statedir.py）。

裝好之後，開新 session 說「幫我設定 OmniKit」，omnikit-setup 會用簡短訪談建立自己的 profile。

參數：
  -ProfileName <名稱>  用這個 profile 的個人規則，並記下來；之後重跑不用再指定。先找 repo 外的
                       ~/.omnikit/profiles/<名稱>（訪談產生的），再找 data/profiles/<名稱>。
  -Dev                 開發／維護模式（開發 OmniKit 本身或 fork 自建名冊時使用）：直連本地工作區、
                       啟用 .githooks 自動同步、不自動切換發行 tag，並檢查 repo git 身分。
  -Edition <模式>      向後相容別名（standard / dev，亦相容舊名 colleague / maintainer）；建議改用 -Dev。
  -Tag <發行標籤>      指定要安裝／升級到的穩定發行 tag（例如 v0.2.1）；未指定時，標準安裝若偵測到
                       v* 發行 tag 會自動鎖定最新穩定 tag。
  -Fresh               這台第一次接上 OmniKit 時使用：把 ~/.claude/CLAUDE.md 受管區塊以外的舊規則
                       備份後移除，避免新舊規則同時生效。
  -WhatIf              預覽：依這台目前的狀態列出會改動的地方，什麼都不做（不下載、不寫檔）；也會跑安裝前檢查。
  -NoBrowser           安裝完成後不自動彈開瀏覽器（背景伺服器仍可按需啟動，或搭配 -NoLaunch 都不啟動）。
  -NoLaunch            安裝完成後不啟動本機控制面板伺服器（CI 或無頭部署用；環境變數 OMNIKIT_NO_LAUNCH=1 同效）。
  -SkipCheck <名稱>    安裝前檢查要略過的項目（已經自己處理好，例如防毒已請 IT 放行：-SkipCheck antivirus）。
  -SelfTest            自我測試：在暫存資料夾與暫存 git repo 測模式判斷、git hook 設定與 profile 的位置，
                       以及 uv 被防毒鎖住時的重試（用假的鎖檔），不動這台的設定。

用法（Windows PowerShell 5.1 或 PowerShell 7）：
  powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\install.ps1 [-ProfileName <名稱>] [-Tag <版本>] [-Dev] [-Fresh] [-NoBrowser] [-NoLaunch] [-WhatIf]
#>
param([string]$ProfileName, [switch]$Dev, [ValidateSet('standard', 'dev', 'colleague', 'maintainer')][string]$Edition, [string]$Tag, [switch]$Fresh, [switch]$WhatIf,
  [switch]$NoBrowser, [switch]$NoLaunch, [switch]$SelfTest, [string[]]$SkipCheck = @())

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
$AgentsPy = Join-Path $Repo 'engine\scripts\sync.py'
$EditionPy = Join-Path $Repo 'engine\scripts\edition.py'
$StatedirPy = Join-Path $Repo 'engine\scripts\statedir.py'
$StatusPy = Join-Path $Repo 'engine\scripts\status.py'
$KitPy = Join-Path $Repo 'engine\scripts\kit.py'
$CockpitPy = Join-Path $Repo 'scripts\cockpit.py'
$PreflightPs1 = Join-Path $Repo 'engine\scripts\preflight.ps1'
$EditionNames = @{ 'standard' = '標準安裝'; 'dev' = '開發模式' }
$EditionAliases = @{ 'standard' = 'standard'; 'dev' = 'dev'; 'colleague' = 'standard'; 'maintainer' = 'dev' }
function Get-NormalizedEdition($raw, [switch]$DevSwitch) {
  $fromRaw = ''
  if ($raw) {
    $k = "$raw".Trim().ToLower()
    if ($EditionAliases.ContainsKey($k)) { $fromRaw = $EditionAliases[$k] }
  }
  if ($DevSwitch -and $fromRaw -and $fromRaw -ne 'dev') {
    throw "參數衝突：不能同時指定 -Dev 與 -Edition $raw"
  }
  if ($DevSwitch) { return 'dev' }
  return $fromRaw
}
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
# 狀態資料夾：跟 statedir.py 一樣是 ~/.omnikit（OMNIKIT_STATE_DIR 可以改），不放 %LOCALAPPDATA%（原因見最上面）
$StateDir = if ($env:OMNIKIT_STATE_DIR) { $env:OMNIKIT_STATE_DIR } else { Join-Path $env:USERPROFILE '.omnikit' }
$AgentsFile = Join-Path $StateDir 'agents.json'
$RecordFile = Join-Path $StateDir 'install-record.json'
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

# 跟 sync.py 的 detect_agents 一樣：看設定資料夾或 PATH 上的指令
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

# 這台是標準安裝還是開發模式（engine/scripts/edition.py）：-Dev 指定的記下來；
# 標準安裝不額外顯示「版本名稱」，僅開發模式提示直連本地工作區與 .githooks
function Resolve-Edition($wanted) {
  $norm = Get-NormalizedEdition $wanted
  $editionArgs = @(if ($norm) { '--set', $norm } else { '--save' })
  $r = Invoke-UvRun (Get-Uv) (@('run', '--quiet', $EditionPy, '--migrate-consent') + $editionArgs + '--show') -Capture
  $value = $r.Output.Trim()
  if ($r.Code -ne 0 -or $value -notin $EditionNames.Keys) { throw "edition.py 失敗（exit $($r.Code)）" }
  if ($value -eq 'dev') {
    Write-Host 'OmniKit 開發模式（-Dev）：直連本地工作區並啟用 .githooks'
  }
  return $value
}

# -WhatIf 用：只判斷不記錄；還沒有 uv 的電腦一定還沒裝過，就是標準安裝
function Get-EditionPreview($wanted) {
  $norm = Get-NormalizedEdition $wanted
  if ($norm) { return $norm }
  if ((Get-Command uv -ErrorAction SilentlyContinue) -or (Test-Path $UvExe)) {
    $value = (Invoke-UvRun (Get-Uv) @('run', '--quiet', $EditionPy, '--show') -Capture).Output.Trim()
    if ($value -in $EditionNames.Keys) { return $value }
  }
  return 'standard'
}

# 免問核准：標準安裝與開發模式統一逐一詢問，本人同意才寫入（預設否；亦可於控制面板工作台開關）
function Request-AutoApprove {
  $r = Invoke-UvRun (Get-Uv) @('run', '--quiet', $AgentsPy, 'approvals', '--ask')
  if ($r.Code -ne 0) { throw "sync.py approvals 失敗（exit $($r.Code)）" }
}

# profile 的資料夾：跟 profiles.py 的 folder 一樣，先找 repo 外的（訪談產生的），再找 repo 裡的；都沒有回 $null
function Get-ProfileDir($name) {
  foreach ($dir in @((Join-Path $StateDir "profiles\$name"), (Join-Path $Repo "data\profiles\$name"))) {
    if (Test-Path -LiteralPath (Join-Path $dir 'AGENTS.md')) { return $dir }
  }
  return $null
}

# -ProfileName 有問題的原因；沒問題回 $null。安裝一開始就檢查，免得下載、寫入到一半才在接上 agent 時失敗
function Test-ProfileName($name) {
  if (-not $name) { return $null }
  if ($name -cnotmatch '^[a-z0-9]+(-[a-z0-9]+)*$') { return "profile 名稱只能用小寫英數與 -：$name" }
  if (-not (Get-ProfileDir $name)) {
    return "找不到 profile「$name」（$(Join-Path $StateDir "profiles\$name") 或 data/profiles/$name，要有 AGENTS.md）"
  }
  return $null
}

# 舊版的狀態位置還有東西的：%LOCALAPPDATA%\omnikit，以及封裝的 app（Claude 桌面版）轉存的副本
# %LOCALAPPDATA%\Packages\<套件>\LocalCache\Local\omnikit（跟 statedir.py 的 candidates 一樣）
function Get-LegacyStateDirs {
  $dirs = @(Join-Path $env:LOCALAPPDATA 'omnikit')
  $pkgs = Join-Path $env:LOCALAPPDATA 'Packages'
  if (Test-Path -LiteralPath $pkgs) {
    $dirs += @(Get-ChildItem -LiteralPath $pkgs -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName 'LocalCache\Local\omnikit' })
  }
  return @($dirs | Where-Object { (Test-Path -LiteralPath $_) -and @(Get-ChildItem -LiteralPath $_ -Force -ErrorAction SilentlyContinue).Count })
}

# 舊位置的狀態合併進 ~/.omnikit（statedir.py）。後面每一步都讀寫新位置，所以 uv 一裝好就先跑
function Merge-LegacyState {
  $r = Invoke-UvRun (Get-Uv) @('run', '--quiet', $StatedirPy, 'migrate', '--quiet')
  if ($r.Code -ne 0) { throw "statedir.py migrate 失敗（exit $($r.Code)）" }
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

# 規則、skills、hooks 與 MCP 都交給無帳本同步器 sync.py（開發模式的 git hook 也用它同步）。
# sync.py 會依各設定目錄的薄 plugin 實際安裝狀態決定寫入權限或備案 hooks，不需額外無條件清掉備案 hooks。
function Connect-Agents($mode = 'standard') {
  $profileArgs = @(if ($ProfileName) { '--profile', $ProfileName })
  $devArgs = @(if ($mode -eq 'dev') { '--dev' } else { '--no-dev' })
  $r = Invoke-UvRun (Get-Uv) (@('run', '--quiet', $AgentsPy, 'connect') + $profileArgs + $devArgs + '--ask')
  if ($r.Code -ne 0) { throw "sync.py connect 失敗（exit $($r.Code)）" }
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

# 標準安裝鎖定穩定發行 tag（v*），不跟著 main 開發中 commit 浮動；-Dev 開發模式維持目前工作分支。
# 不用 2>$null：PowerShell 5.1 在 Stop 模式下會把原生指令的 stderr 當成錯誤丟出。
function Get-LatestReleaseTag($repoPath) {
  $tags = @(git -C $repoPath tag -l 'v*' --sort=-v:refname | Where-Object { $_ -and $_.Trim() })
  if ($tags.Count -gt 0) { return $tags[0].Trim() }
  return $null
}

function Get-CurrentTag($repoPath) {
  $tags = @(git -C $repoPath tag --points-at HEAD | Where-Object { $_ -and $_.Trim() })
  if ($tags.Count -gt 0) { return $tags[0].Trim() }
  return $null
}

function Switch-ReleaseTag($mode, $requestedTag) {
  if ($mode -eq 'dev') { return $null }
  $curTag = Get-CurrentTag $Repo
  $target = if ($requestedTag) { $requestedTag.Trim() } else { $null }
  if ($target) {
    $matched = @(git -C $Repo tag -l -- $target | Where-Object { $_.Trim() -eq $target })
    if (-not $matched) { throw "找不到發行 tag「$target」，請先執行 git fetch --tags 並確認版本名稱" }
  } elseif ($curTag) {
    Write-Host "OmniKit 穩定發行版本：$curTag"
    return $curTag
  } else {
    $target = Get-LatestReleaseTag $Repo
    if (-not $target) {
      Write-Host '提示：目前 repo 尚未建立發行 tag（v*），暫以目前版本安裝；正式發版後將自動鎖定最新穩定 tag。'
      return $null
    }
  }
  if ($curTag -eq $target) {
    Write-Host "OmniKit 已在穩定發行版本：$target"
    return $target
  }
  $dirty = @(git -C $Repo status --porcelain | Where-Object { $_ -and $_.Trim() })
  if ($dirty.Count -gt 0) {
    throw "repo 有尚未提交的本機變更，無法切換到發行 tag「$target」；請先處理變更後重跑"
  }
  git -C $Repo -c advice.detachedHead=false checkout --quiet $target
  if ($LASTEXITCODE -ne 0) { throw "切換到發行 tag「$target」失敗（exit $LASTEXITCODE）" }
  Write-Host "OmniKit 已切換至穩定發行版本：$target"
  return $target
}

# 開發模式（-Dev）：commit 前掃金鑰、驗證名冊，commit 或 pull 後自動同步。
# 標準安裝不設 git hook，pull 不會改任何設定；以前設過的拿掉
function Set-GitHooks($mode) {
  if ($mode -eq 'dev') {
    git -C $Repo config core.hooksPath .githooks
  } elseif ((git -C $Repo config --get core.hooksPath) -eq '.githooks') {
    git -C $Repo config --unset core.hooksPath
    Write-Host '已停用這個 repo 的 .githooks，pull 不會自動改設定'
  }
}

function Test-GitIdentity {
  $email = git -C $Repo config user.email
  Write-Host "OmniKit 的 git 身分：$(git -C $Repo config user.name) <$email>"
  if ($email -notmatch '@users\.noreply\.github\.com$') {
    Write-Warning "這不是 GitHub noreply 信箱，commit 到公開 repo 會公開它。可以只在這個 repo 改設：git -C `"$Repo`" config user.email <noreply 信箱>"
  }
}

# 判斷是否允許啟動本機控制面板伺服器（CI、SSH、Session 0、-NoLaunch、OMNIKIT_NO_LAUNCH 時一律略過）
function Test-CanLaunchServer([switch]$ForceNoLaunch) {
  if ($ForceNoLaunch -or $NoLaunch) { return $false }
  foreach ($v in @($env:OMNIKIT_NO_LAUNCH, $env:CI, $env:GITHUB_ACTIONS, $env:TF_BUILD, $env:SSH_CONNECTION, $env:SSH_CLIENT)) {
    if ($v -and "$v".Trim() -notin @('', '0', 'false', 'False')) { return $false }
  }
  try {
    if (-not [Environment]::UserInteractive) { return $false }
  } catch { }
  try {
    if ((Get-Process -Id $PID -ErrorAction SilentlyContinue).SessionId -eq 0) { return $false }
  } catch { }
  return $true
}

# 判斷是否自動在桌面開啟預設瀏覽器（額外檢查 -NoBrowser 與 OMNIKIT_NO_BROWSER）
function Test-CanOpenUi([switch]$ForceNoBrowser, [switch]$ForceNoLaunch) {
  if ($ForceNoBrowser -or $NoBrowser) { return $false }
  if ($env:OMNIKIT_NO_BROWSER -and "$($env:OMNIKIT_NO_BROWSER)".Trim() -notin @('', '0', 'false', 'False')) { return $false }
  return (Test-CanLaunchServer -ForceNoLaunch:$ForceNoLaunch)
}

# Preflight 僅缺 npm 時允許降級繼續安裝（規則、核心技能、防假完工與本機控制面板不依賴 Node.js）
function Test-PreflightAllowsContinue($results) {
  $failed = @($results | Where-Object { -not $_.ok } | ForEach-Object { $_.name })
  if ($failed.Count -eq 0) { return @{ Ok = $true; WarnOnlyNpm = $false } }
  if ($failed.Count -eq 1 -and $failed[0] -eq 'npm') { return @{ Ok = $true; WarnOnlyNpm = $true } }
  return @{ Ok = $false; WarnOnlyNpm = $false }
}

function Invoke-SafeBrowserOpen($url, [scriptblock]$Opener = $null) {
  try {
    if ($Opener) { & $Opener $url } else { Start-Process $url | Out-Null }
    return $true
  } catch {
    Write-Warning "無法自動開啟瀏覽器（$($_.Exception.Message)），請手動在瀏覽器開啟：$url"
    return $false
  }
}

# 初始化零帳號本機狀態板（NOW.md）與預設免金鑰精選工作台
function Initialize-LocalWorkbench {
  $rSt = Invoke-UvRun (Get-Uv) @('run', '--quiet', $StatusPy, 'init') -Capture
  if ($rSt.Code -ne 0) {
    Write-Warning "初始化本機狀態板略過（$($rSt.Error)）"
  }
  $rKit = Invoke-UvRun (Get-Uv) @('run', '--quiet', $KitPy, '--state-dir', $StateDir, '--repo-root', $Repo, 'init-workbench') -Capture
  if ($rKit.Code -ne 0) {
    Write-Warning "初始化工作台設定略過（exit $($rKit.Code)：$($rKit.Error)）"
  } elseif ($rKit.Error -and $rKit.Error.Trim()) {
    $rKit.Error.Trim().Split("`n") | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkYellow }
  }
}

# 在開始功能表建立「OmniKit 控制面板.lnk」（包在 try/catch 內，絕不讓捷徑失敗中斷安裝）
function New-ControlPanelShortcut {
  if (-not (Test-CanLaunchServer)) { return }
  try {
    $programsMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
    if (-not (Test-Path -LiteralPath $programsMenu)) { return }
    $lnk = Join-Path $programsMenu 'OmniKit 控制面板.lnk'
    $psExe = Join-Path ($env:SystemRoot) 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $uvPath = Get-Uv
    $escUv = "$uvPath".Replace("'", "''")
    $escCockpit = "$CockpitPy".Replace("'", "''")
    $sh = New-Object -ComObject WScript.Shell
    $s = $sh.CreateShortcut($lnk)
    $s.TargetPath = $psExe
    $s.Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -Command `"& '$escUv' run '$escCockpit' open`""
    $s.WorkingDirectory = $Repo
    $s.WindowStyle = 7
    $s.Description = '開啟 OmniKit 本機控制面板'
    $s.Save()
    Add-InstallRecord shortcuts $lnk
  } catch {
    # 捷徑屬輔助入口，失敗不警告、不阻斷
  }
}

function Start-ControlPanelIfAllowed {
  if (-not (Test-CanLaunchServer)) { return $null }
  try {
    $r = Invoke-UvRun (Get-Uv) @('run', '--quiet', $CockpitPy, '--state-dir', $StateDir, 'launch', '--json') -Capture
    if ($r.Code -eq 0 -and $r.Output.Trim()) {
      $doc = $r.Output.Trim() | ConvertFrom-Json
      if ($doc.ok -and $doc.url) {
        if (Test-CanOpenUi) { [void](Invoke-SafeBrowserOpen $doc.url) }
        return $doc.url
      }
    }
  } catch {
    Write-Warning "本機控制面板自動啟動略過（可隨時執行 uv run ~/.omnikit/current/scripts/cockpit.py open 開啟）"
  }
  return $null
}

# -WhatIf：依這台目前的狀態列出會改動的地方，什麼都不做（不下載、不寫檔）
function Show-InstallPlan {
  $requested = Get-NormalizedEdition $Edition -DevSwitch:$Dev
  $mode = Get-EditionPreview $requested
  $plan = @()
  if ($mode -eq 'dev') {
    $plan += '模式：開發模式（-Dev，直連本地工作區、commit 或 pull 後由 .githooks 自動同步）'
  } else {
    $curTag = Get-CurrentTag $Repo
    $latestTag = Get-LatestReleaseTag $Repo
    if ($Tag) {
      $plan += "發行版本：切換至指定 tag「$Tag」"
    } elseif ($curTag) {
      $plan += "發行版本：維持目前的穩定 tag「$curTag」"
    } elseif ($latestTag) {
      $plan += "發行版本：自動切換至最新穩定 tag「$latestTag」"
    } else {
      $plan += '發行版本：repo 尚未建立 v* 發行 tag，暫以目前版本安裝'
    }
  }
  $tools = @(
    @{ Name = 'uv'; Version = $UvVersion; Path = $UvExe; Command = 'uv' },
    @{ Name = 'gh'; Version = $GhVersion; Path = $GhExe; Command = 'gh' },
    @{ Name = 'gitleaks'; Version = $GitleaksVersion; Path = $GitleaksExe; Command = 'gitleaks' }
  )
  foreach ($t in $tools) {
    $onPath = $t.Command -and (Get-Command $t.Command -ErrorAction SilentlyContinue)
    if (-not $onPath -and -not (Test-Path $t.Path)) {
      $plan += "下載 $($t.Name) $($t.Version)，比對 SHA256 後放到 $(Split-Path $t.Path)（不改 PATH）"
    }
  }

  if ($mode -eq 'dev') {
    $url = git -C $Repo remote get-url origin
    $config = [IO.File]::ReadAllText((Join-Path $Repo 'data\omnikit.yaml'), [Text.Encoding]::UTF8)
    if ($url -match 'github\.com[:/]([^/]+)/([^/]+?)(\.git)?/?$' -and $config -notmatch "(?m)^repo: $([regex]::Escape("$($Matches[1])/$($Matches[2])"))\s*$") {
      $plan += "data/omnikit.yaml 改成 $($Matches[1])/$($Matches[2])、看板用的 profile 改回 default，重新產生 marketplace 清單"
    }
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
  $legacyState = @(Get-LegacyStateDirs)
  if ($legacyState) {
    $plan += "  狀態檔改放 $StateDir：把舊位置（$($legacyState -join '、')）合併過去，舊的原封不動備份在 $(Join-Path $StateDir 'legacy')；兩份不一樣的用較新的，並列出來"
  }
  $legacyProfiles = @(Get-LegacyProfiles)
  if ($legacyProfiles) {
    $dest = Join-Path $StateDir 'profiles'
    $plan += "  舊版存在 repo 裡的 profile（$($legacyProfiles -join '、')）：搬到 $dest（不會被 commit）；刪掉 repo 裡的舊檔前先問你，不能互動時不搬"
  }
  $stateFile = Join-Path $StateDir 'profile.json'
  # 還沒合併：預覽照舊位置的記錄
  if (-not (Test-Path -LiteralPath $stateFile)) {
    $stateFile = @($legacyState | ForEach-Object { Join-Path $_ 'profile.json' } | Where-Object { Test-Path -LiteralPath $_ }) + @($stateFile) | Select-Object -First 1
  }
  $chosen = if (Test-Path -LiteralPath $stateFile) { try { ([IO.File]::ReadAllText($stateFile) | ConvertFrom-Json).profile } catch { $null } }
  $name = if ($ProfileName) { $ProfileName } elseif ($chosen) { $chosen } else { 'default' }
  $note = if ($ProfileName -or $chosen) { '' } else { '（還沒選過，用預設：下載、安裝前會先問）' }
  $profileDir = Get-ProfileDir $name
  $where = if (-not $profileDir) { '' } elseif ($profileDir.StartsWith($Repo)) { "，data/profiles/$name" } else { "，$profileDir" }
  $plan += "  規則：安全底線 + profile「$name」$note$where"
  if (-not $profileDir) {
    $plan += "  找不到 profile「$name」（$(Join-Path $StateDir "profiles\$name") 或 data/profiles/$name，要有 AGENTS.md），安裝會在這一步失敗"
  }
  if ($agents -contains 'claude-code') {
    $verb = if ((Get-FileText $ClaudeMd) -match $BlockPattern) { '更新' } else { '在開頭加上' }
    $plan += "  ~/.claude/CLAUDE.md：$($verb)受管區塊，import 底線與 profile（附帶內金絲雀行）；其他內容不動"
    $plan += '  其他設定目錄（CLAUDE_CONFIG_DIR、CODEX_HOME、T3 Code 的實例、config.json 額外列舉目錄，見 homes.py）：規則放受管區塊，Claude 與 Codex 的 skills 以 Directory Junction 連入，薄 plugin／MCP 與權限設定一併同步'
  }
  if ($agents -contains 'antigravity' -and (Test-Path (Join-Path $env:USERPROFILE '.t3\userdata\settings.json'))) {
    $plan += '  T3 Code 的 Antigravity 實例：於各實例放置 config/plugins/omnikit/ 薄 plugin（護欄與 MCP）；規則與 skills.json 由 T3 原生同步 ~/.gemini（舊版 ACP 轉接程式會自動清理）'
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
      $plan += '  ~/.gemini/AGENTS.md（共用）與 GEMINI.md（個人）：更新受管區塊（單檔 <= 24,000 bytes）；其他內容不動'
    } elseif ($gemini.Trim()) {
      $plan += '  ~/.gemini/AGENTS.md（共用）與 GEMINI.md（個人）：先備份既有檔成 .pre-omnikit，在開頭加上受管區塊（原地改寫，單檔 <= 24,000 bytes）'
    } else {
      $plan += '  ~/.gemini/AGENTS.md（共用）與 GEMINI.md（個人）：建立底線與 profile 受管區塊（單檔 <= 24,000 bytes）'
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
  if ($agents -contains 'claude-code') { $plan += "  skills：$skills 以 Directory Junction 連到 ~/.claude/skills（來源 ~/.omnikit/current/engine/skills，零複製）" }
  if ($agents -contains 'codex') { $plan += "  skills：$skills 以 Directory Junction 連到 ~/.codex/skills（來源 ~/.omnikit/current/engine/skills，並清理舊 ~/.agents/skills 殘留）" }
  if ($agents -contains 'antigravity') { $plan += "  skills：更新 ~/.gemini/config/skills.json 原生參照 ~/.omnikit/current/engine/skills（T3 自動同步至全部實例，並清理舊 ~/.gemini/config/skills 複製品）" }
  $servers = [regex]::Matches((Get-FileText (Join-Path $Repo 'data\mcp\servers.yaml')), '(?m)^  ([A-Za-z0-9_-]+):\s*$') |
    ForEach-Object { $_.Groups[1].Value }
  $mcpTargets = @{
    'claude-code' = 'Claude 本地薄 plugin（~/.omnikit/claude-marketplace -> omnikit@omnikit-local，不動頂層 ~/.claude.json）'
    'codex'       = 'Codex CLI（~/.codex/config.toml）'
    'antigravity' = 'Antigravity 薄 plugin（~/.gemini/config/plugins/omnikit/ 與各 T3 實例，不動頂層 mcp_config.json）'
  }
  if ($servers -and $agents) {
    $plan += "  MCP（$($servers -join '、')）：無帳本對帳掛載至 $(($agents | ForEach-Object { $mcpTargets[$_] }) -join '；')"
  }
  $ssText = Get-FileText $SkillshareConfig
  if ($ssText -match '(?m)^\s*- name: rules-codex\s*$' -or $ssText -match '(?m)^  mcp: .*servers\.yaml' -or
      (Test-Path (Join-Path $env:APPDATA 'skillshare\skills\_omnikit'))) {
    $plan += '  不再使用 skillshare：改由 OmniKit 接手，拿掉 skillshare 設定裡 OmniKit 的部分（skillshare 本身不刪）'
  }

  $allow = @(Get-Content -Encoding UTF8 (Join-Path $Repo 'data\harness\claude-allow.txt') |
    ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
  if ($allow) {
    # 跟 edition.py 的 tool_of 一樣：mcp__<server>（__<工具>）算在那個 server
    $approveTools = @($allow | ForEach-Object { $_ -replace '^mcp__(.+?)(__.+)?$', '$1' } | Select-Object -Unique)
    $plan += "免問核准（$($approveTools -join '、')）：安裝時逐一問你或於控制面板工作台調整，同意了才寫進 ~/.claude/settings.json 與 ~/.codex/config.toml（預設否）"
  }
  if ($agents -contains 'claude-code') {
    $plan += 'Claude 護欄與提醒 hooks：透過本地薄 plugin（omnikit@omnikit-local）掛載確定性護欄、開新對話提醒、說做不到查證、設定目錄檢查與 T3 MCP 防護（找不到 claude CLI 時退回 settings.json hooks 備案），並寫入 statusLine；其他 Claude 設定目錄一併同步'
  }
  if ($agents -contains 'codex') {
    $plan += 'Codex hooks：加進 ~/.codex/config.toml（開新對話提醒、說做不到查證與 T3 MCP 防護；需到 /hooks 信任才會跑）'
  }
  if ($agents -contains 'antigravity') {
    $plan += 'Antigravity 護欄 hooks：透過 ~/.gemini/config/plugins/omnikit/hooks.json（與各 T3 實例）掛載確定性護欄'
  }
  $hooksOn = (git -C $Repo config --get core.hooksPath) -eq '.githooks'
  if ($mode -eq 'dev' -and -not $hooksOn) {
    $plan += '這個 repo 改用 .githooks：commit 前掃金鑰、驗證名冊；改到規則、skills、MCP 等檔案時自動同步'
  } elseif ($mode -ne 'dev' -and $hooksOn) {
    $plan += '這個 repo 不再使用 .githooks：標準安裝不設 git hook，pull 不會自動改設定'
  } elseif ($mode -ne 'dev') {
    $plan += '不設 git hook：pull 不會自動改設定；要套用更新就重跑 install.ps1（先用 -WhatIf 預覽）'
  }

  $plan += "初始化零帳號本機狀態板（$(Join-Path $StateDir 'status')）與預設免金鑰精選工作台（$(Join-Path $StateDir 'kit.yaml')）"
  if (Test-CanLaunchServer) {
    $uiNote = if (Test-CanOpenUi) { '並自動在預設瀏覽器開啟' } else { '（不自動彈開瀏覽器）' }
    $plan += "啟動本機控制面板（http://127.0.0.1:3780/）$uiNote"
  }

  Write-Host '這是預覽，什麼都沒改。照這台目前的狀態，install.ps1 會：'
  # 兩個空白開頭的是上一項的細節，縮排顯示
  $plan | ForEach-Object { if ($_.StartsWith('  ')) { Write-Host "      $($_.Trim())" } else { Write-Host "  - $_" } }
  Write-Host ''
  Write-Host '拿掉 -WhatIf 再執行就會照做；每一項的說明見 docs/install.md 的「安裝會改動哪些地方」。'
}

# 安裝完成後提示本機控制面板入口、零帳號狀態板與日常指令
function Show-NextSteps($mode, $panelUrl = $null) {
  $text = [IO.File]::ReadAllText((Join-Path $Repo 'data\rules\baseline.md'), [Text.Encoding]::UTF8)
  $version = if ($text -match '規則版本：(\S+)') { $Matches[1] } else { 'data/rules/baseline.md 開頭的版本' }
  $name = (Invoke-UvRun (Get-Uv) @('run', '--quiet', $ProfilesPy, '--show') -Capture).Output.Trim()
  $cfgFile = Join-Path $StateDir 'config.json'
  $record = if (Test-Path $cfgFile) { try { [IO.File]::ReadAllText($cfgFile) | ConvertFrom-Json } catch { $null } } else { try { [IO.File]::ReadAllText($AgentsFile) | ConvertFrom-Json } catch { $null } }
  $connected = @($record.agents | Where-Object { $_ } | ForEach-Object { $AgentNames[$_] })
  Write-Host ''
  Write-Host "OmniKit 已接上 $($connected -join '、')（profile：$name），新開的對話將套用防假完工護欄與精選工作台。" -ForegroundColor Green
  Write-Host ''
  if ($panelUrl) {
    Write-Host "本機控制面板已啟動：$panelUrl" -ForegroundColor Cyan
    Write-Host '  - 直接在瀏覽器勾選偏好與精選套件，一鍵套用即可（免建 GitHub 私人 repo 即可使用本機 NOW.md 狀態板）' -ForegroundColor Cyan
  } else {
    Write-Host '開啟本機控制面板：uv run ~/.omnikit/current/scripts/cockpit.py open（或在對話輸入 /ok 面板）' -ForegroundColor Cyan
  }
  Write-Host ''
  Write-Host '日常快捷指令：'
  Write-Host '  - 開啟面板或查看狀態：在對話輸入 /ok（或 /ok 面板）'
  Write-Host '  - 防假完工實體驗收：在對話輸入 /ok 驗收（自動檢查假綠燈並真開服務／瀏覽器確認 0 錯誤）'
  Write-Host "  - 確認連線版本：問「OmniKit 規則版本與 profile 是什麼？」，應回答 $version 與 $name"
  if ($mode -ne 'dev') {
    Write-Host '  - 版本更新：預設鎖定穩定發行 tag；升級時先 git fetch --tags --force; git checkout <新版本>，再跑 install.ps1 -Tag <新版本>'
  }
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
  $realStateEnv, $realStateDir = $env:OMNIKIT_STATE_DIR, $script:StateDir
  # uv 的快取預設在 %LOCALAPPDATA%，換掉之前先指回原本的，免得重新下載
  if (-not $env:UV_CACHE_DIR) { $env:UV_CACHE_DIR = Join-Path $realLocal 'uv\cache' }
  try {
    $env:LOCALAPPDATA = Join-Path $tmp 'local'
    $env:OMNIKIT_STATE_DIR = Join-Path $tmp 'state'
    $script:StateDir = $env:OMNIKIT_STATE_DIR
    $editionFile = Join-Path $script:StateDir 'edition.json'
    Check 'Get-EditionPreview：沒有記錄是標準安裝（standard），而且不寫檔' ((Get-EditionPreview '') -eq 'standard' -and -not (Test-Path $editionFile))
    Check 'Resolve-Edition：沒指定就照判斷（standard）並記下來' ((Resolve-Edition '') -eq 'standard' -and (Get-FileText $editionFile) -match '"standard"')
    Check 'Resolve-Edition：-Dev 記成開發模式（dev）' ((Resolve-Edition 'dev') -eq 'dev' -and (Get-FileText $editionFile) -match '"dev"')
    Check 'Resolve-Edition：之後沒指定就沿用記錄' ((Resolve-Edition '') -eq 'dev')
    Check 'Get-EditionPreview：照記錄' ((Get-EditionPreview '') -eq 'dev')
    Check 'Get-EditionPreview：支援舊別名 colleague / maintainer 正規化' ((Get-EditionPreview 'colleague') -eq 'standard' -and (Get-EditionPreview 'maintainer') -eq 'dev')

    $script:Repo = Join-Path $tmp 'repo'
    git init --quiet $script:Repo
    git -C $script:Repo config core.hooksPath .githooks
    Set-GitHooks 'standard'
    Check 'Set-GitHooks standard：拿掉以前設的 .githooks，pull 不會自動同步' (-not (git -C $script:Repo config --get core.hooksPath))
    Set-GitHooks 'standard'
    Check 'Set-GitHooks standard：本來就沒設，不出錯' (-not (git -C $script:Repo config --get core.hooksPath))
    Set-GitHooks 'dev'
    Check 'Set-GitHooks dev：設成 .githooks' ((git -C $script:Repo config --get core.hooksPath) -eq '.githooks')

    # 標準安裝發行 tag 鎖定：自然版本排序、自動切到最新 tag、指定 -Tag、開發模式不動分支、髒工作區拒絕切換
    $tagRepo = Join-Path $tmp 'tr'
    git -c core.longpaths=true init --quiet $tagRepo
    git -C $tagRepo config core.longpaths true
    git -C $tagRepo config user.name 'selftest'
    git -C $tagRepo config user.email 'selftest@example.com'
    git -C $tagRepo config core.autocrlf false
    $savedTagRepo = $script:Repo
    $script:Repo = $tagRepo
    try {
      [IO.File]::WriteAllText((Join-Path $tagRepo 'f.txt'), "v1`n", (New-Object Text.UTF8Encoding($false)))
      git -C $tagRepo add f.txt
      git -C $tagRepo commit --quiet -m 'c1'
      Check 'Get-LatestReleaseTag：無 tag 時回 $null，標準安裝不報錯' ($null -eq (Get-LatestReleaseTag $tagRepo) -and $null -eq (Switch-ReleaseTag 'standard' ''))
      git -C $tagRepo tag v0.1.0
      [IO.File]::WriteAllText((Join-Path $tagRepo 'f.txt'), "v2`n", (New-Object Text.UTF8Encoding($false)))
      git -C $tagRepo commit --quiet -am 'c2'
      git -C $tagRepo tag v0.2.0
      [IO.File]::WriteAllText((Join-Path $tagRepo 'f.txt'), "v10`n", (New-Object Text.UTF8Encoding($false)))
      git -C $tagRepo commit --quiet -am 'c3'
      git -C $tagRepo tag v0.10.0
      [IO.File]::WriteAllText((Join-Path $tagRepo 'f.txt'), "dev`n", (New-Object Text.UTF8Encoding($false)))
      git -C $tagRepo commit --quiet -am 'c4-dev'
      $devBranch = (git -C $tagRepo branch --show-current).Trim()
      Check 'Get-LatestReleaseTag：語意版本自然排序 v0.10.0 > v0.2.0' ((Get-LatestReleaseTag $tagRepo) -eq 'v0.10.0')
      $mRes = Switch-ReleaseTag 'dev' ''
      Check 'Switch-ReleaseTag dev：維持原分支不切換' ($null -eq $mRes -and (git -C $tagRepo branch --show-current).Trim() -eq $devBranch)
      $cRes = Switch-ReleaseTag 'standard' ''
      Check 'Switch-ReleaseTag standard：未指定 -Tag 時自動切換到最新穩定 tag（略過未發版 commit）' ($cRes -eq 'v0.10.0' -and (Get-CurrentTag $tagRepo) -eq 'v0.10.0')
      $pRes = Switch-ReleaseTag 'standard' 'v0.1.0'
      Check 'Switch-ReleaseTag standard -Tag v0.1.0：切換到指定發行 tag' ($pRes -eq 'v0.1.0' -and (Get-CurrentTag $tagRepo) -eq 'v0.1.0')
      [IO.File]::WriteAllText((Join-Path $tagRepo 'f.txt'), "dirty`n", (New-Object Text.UTF8Encoding($false)))
      $dirtyBlocked = $false
      try { [void](Switch-ReleaseTag 'standard' 'v0.10.0') } catch { $dirtyBlocked = $_.Exception.Message -match '尚未提交' }
      Check 'Switch-ReleaseTag：工作區有未提交變更時拒絕切換' $dirtyBlocked
    } finally {
      $script:Repo = $savedTagRepo
    }

    # profile 的位置（FR-38）：訪談產生的在 repo 外，同名時優先；舊版存在 repo 裡、沒進版本控制的要搬
    $utf8 = New-Object Text.UTF8Encoding($false)
    $put = { param($path, $text) New-Item -ItemType Directory -Force -Path (Split-Path $path) | Out-Null; [IO.File]::WriteAllText($path, $text, $utf8) }
    $inRepo = Join-Path $script:Repo 'data\profiles'
    $local = Join-Path $script:StateDir 'profiles'
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

    # 狀態的舊位置：%LOCALAPPDATA%\omnikit 與封裝的 app 轉存的副本，有東西的才算；合併後就不算
    $pkgCopy = Join-Path $env:LOCALAPPDATA 'Packages\Claude_x\LocalCache\Local\omnikit'
    New-Item -ItemType Directory -Force -Path (Join-Path $env:LOCALAPPDATA 'Packages\Other_y\LocalCache\Local') | Out-Null
    & $put (Join-Path $pkgCopy 'agents.json') '{"agents": ["claude-code"]}'
    & $put (Join-Path $env:LOCALAPPDATA 'omnikit\edition.json') '{"edition": "maintainer"}'
    New-Item -ItemType Directory -Force -Path (Join-Path $env:LOCALAPPDATA 'Packages\Empty_z\LocalCache\Local\omnikit') | Out-Null
    Check 'Get-LegacyStateDirs：列出有東西的舊位置（空的不算）' ((@(Get-LegacyStateDirs) -join '|') -eq
      ((Join-Path $env:LOCALAPPDATA 'omnikit'), $pkgCopy -join '|'))
    Merge-LegacyState
    Check 'Merge-LegacyState：合併進狀態資料夾，舊位置搬走' (@(Get-LegacyStateDirs).Count -eq 0 -and
      (Get-FileText (Join-Path $script:StateDir 'agents.json')) -match 'claude-code' -and
      (Get-FileText (Join-Path $script:StateDir 'edition.json')) -match 'maintainer')

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

    # 無頭環境抑制與瀏覽器例外安全攔截（P0-1 / Gap 6）
    $savedCi, $savedNoBr, $savedNoLn = $env:CI, $env:OMNIKIT_NO_BROWSER, $env:OMNIKIT_NO_LAUNCH
    try {
      $env:CI = '1'
      Check 'CI=1 時自動抑制伺服器與瀏覽器啟動' (-not (Test-CanLaunchServer) -and -not (Test-CanOpenUi))
      $env:CI = ''
      $env:OMNIKIT_NO_BROWSER = '1'
      Check 'OMNIKIT_NO_BROWSER=1 時抑制自動開啟瀏覽器' (-not (Test-CanOpenUi))
    } finally {
      $env:CI, $env:OMNIKIT_NO_BROWSER, $env:OMNIKIT_NO_LAUNCH = $savedCi, $savedNoBr, $savedNoLn
    }
    $openSafe = Invoke-SafeBrowserOpen 'http://127.0.0.1:3780/' -Opener { param($u) throw "模擬預設瀏覽器錯誤 $u" } 3>$null
    Check 'Invoke-SafeBrowserOpen：瀏覽器啟動拋出例外時安全攔截回傳 $false，不讓安裝腳本非零退出' ($openSafe -eq $false)

    $pfOnlyNpm = Test-PreflightAllowsContinue @([pscustomobject]@{name='git';ok=$true}, [pscustomobject]@{name='npm';ok=$false})
    $pfNoGit = Test-PreflightAllowsContinue @([pscustomobject]@{name='git';ok=$false}, [pscustomobject]@{name='npm';ok=$false})
    Check 'Test-PreflightAllowsContinue：僅缺 npm 時允許降級繼續；缺 git 等硬性條件時嚴格阻斷' ($pfOnlyNpm.Ok -and $pfOnlyNpm.WarnOnlyNpm -and -not $pfNoGit.Ok)
  } finally {
    $env:LOCALAPPDATA, $script:Repo, $env:UV_CACHE_DIR = $realLocal, $realRepo, $realUvCache
    $env:OMNIKIT_STATE_DIR, $script:StateDir = $realStateEnv, $realStateDir
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

# 安裝前檢查（FR-35）：硬性條件不通過就什麼都不下載、不寫入；僅缺 npm 時降級提示繼續安裝
& $PreflightPs1 -Skip $SkipCheck
$PreflightOk = ($LASTEXITCODE -eq 0)
$WarnOnlyNpm = $false
if (-not $PreflightOk) {
  try {
    $pfJson = (& $PreflightPs1 -Json -Skip $SkipCheck) | ConvertFrom-Json
    $pfEval = Test-PreflightAllowsContinue @($pfJson)
    if ($pfEval.Ok -and $pfEval.WarnOnlyNpm) {
      $PreflightOk = $true
      $WarnOnlyNpm = $true
    }
  } catch { }
}
Write-Host ''
if ($WarnOnlyNpm) {
  Write-Host '提示：這台尚未安裝 Node.js / npm，將先安裝 OmniKit 規則、核心技能、防假完工護欄與本機控制面板；需要 Node 的 MCP 套件待安裝 Node.js LTS 後重跑即可補上。' -ForegroundColor Yellow
  Write-Host ''
}
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
Merge-LegacyState
Install-Gh
$RequestedMode = Get-NormalizedEdition $Edition -DevSwitch:$Dev
$CurrentMode = Resolve-Edition $RequestedMode
[void](Switch-ReleaseTag $CurrentMode $Tag)
Install-Gitleaks
if ($CurrentMode -eq 'dev') { Sync-RepoConfig }
Install-McpPackages
Request-AutoApprove
Move-LegacyProfiles
Connect-Agents $CurrentMode
Initialize-LocalWorkbench
New-ControlPanelShortcut
if ($Fresh) { Clear-OldClaudeRules }
Set-GitHooks $CurrentMode
if ($CurrentMode -eq 'dev') { Test-GitIdentity }
$PanelUrl = Start-ControlPanelIfAllowed
Show-NextSteps $CurrentMode $PanelUrl
