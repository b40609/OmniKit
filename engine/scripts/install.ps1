<#
OmniKit 安裝：把這台 Windows 電腦接上 OmniKit，可以重複執行。

1. 安裝固定版本的 skillshare、uv、gh 與 gitleaks：從 GitHub release 下載 zip，比對寫死的
   SHA256 後解壓；不改 PATH。這台已經有 uv 或 gh 就沿用。
2. fork 出來的 repo：把 data/omnikit.yaml 的 repo、owner、marketplace 改成 origin 指向的
   GitHub repo，並重新產生 marketplace 清單，避免跟原作者的 marketplace 撞名。
3. 第一次執行時初始化 skillshare，target 是 Claude Code 與 Codex。
4. 把 data/rules/AGENTS.md 接到兩邊：Claude 用 import，Codex 用複製（第一次接上時，
   原本的 ~/.codex/AGENTS.md 先備份），然後同步；engine/skills 裡的 skills 也連進
   skillshare，同步到兩邊。
5. 依 data/mcp/packages.txt 全域安裝 MCP 用的 npm 套件（固定版本），
   再把 data/mcp/servers.yaml 設成 skillshare 的 MCP 來源，同步到兩邊。
6. 把 data/harness/claude-allow.txt 的權限規則補進 Claude Code 的使用者設定（只增不刪）。
7. 設定 git hook：commit 前驗證名冊；commit 或 pull 動到規則、MCP 或權限規則時，自動同步。
8. 檢查 OmniKit repo 的 git 身分。

參數：
  -Fresh  這台第一次接上 OmniKit 時使用：把 ~/.claude/CLAUDE.md 受管區塊以外的舊規則
          備份後移除，避免新舊規則同時生效。

用法（Windows PowerShell 5.1 或 PowerShell 7）：
  powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\install.ps1 [-Fresh]
#>
param([switch]$Fresh)

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
$Rules = Join-Path $Repo 'data\rules'
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

# 下載 release zip，SHA256 相符才把指定的執行檔放進 $dest
function Install-PinnedZip($url, $sha256, $exeNames, $dest) {
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
  } finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
  }
}

function Install-Skillshare {
  if ((Test-Path $Exe) -and ((& $Exe --version 2>$null) -match [regex]::Escape($SkillshareVersion))) {
    Write-Host "skillshare $SkillshareVersion 已安裝：$Exe"
    return
  }
  $url = "https://github.com/runkids/skillshare/releases/download/v$SkillshareVersion/skillshare_${SkillshareVersion}_windows_$Arch.zip"
  Install-PinnedZip $url $SkillshareSha256[$Arch] @('skillshare.exe') $BinDir
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
  [IO.File]::WriteAllText($config, $text, (New-Object Text.UTF8Encoding($false)))
  & (Get-Uv) run --quiet (Join-Path $Repo 'engine\scripts\build.py') --marketplace-only | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "build.py --marketplace-only 失敗（exit $LASTEXITCODE）" }
  Write-Host "已把 data/omnikit.yaml 與 marketplace 清單改成 $owner/$name，記得 commit"
}

function Initialize-Skillshare {
  if (Test-Path (Join-Path $env:APPDATA 'skillshare\config.yaml')) { return }
  Invoke-Skillshare init --no-copy --no-git --no-skill --targets claude,codex --no-tui
}

# skillshare 0.28.2 的 import 模式在 Windows 寫出反斜線路徑，Claude Code 不會載入；
# 所以 Claude 這邊自己維護受管區塊，路徑改用正斜線
function Connect-ClaudeRules {
  $import = '@' + (Join-Path $Rules 'AGENTS.md').Replace('\', '/')
  $block = "<!-- omnikit:rules:begin -->`n$import`n<!-- omnikit:rules:end -->"
  $text = if (Test-Path $ClaudeMd) { [IO.File]::ReadAllText($ClaudeMd, [Text.Encoding]::UTF8) } else { '' }
  if ($text -match $BlockPattern) { $text = [regex]::Replace($text, $BlockPattern, { $block }) }
  else { $text = $block + "`n" + $text }
  [IO.File]::WriteAllText($ClaudeMd, $text, (New-Object Text.UTF8Encoding($false)))
}

# Codex 不支援 import，由 skillshare 複製一份；--force 讓重複執行時覆寫成同一份定義。
# 第一次接上時（skillshare 還沒有 rules-codex），原本的 ~/.codex/AGENTS.md 先備份
function Connect-CodexRules {
  $config = Join-Path $env:APPDATA 'skillshare\config.yaml'
  $managed = [IO.File]::ReadAllText($config, [Text.Encoding]::UTF8) -match '(?m)^\s*- name: rules-codex\s*$'
  if (-not $managed -and (Test-Path $CodexMd)) {
    Write-Host "已備份原本的 Codex 規則：$(Backup-File $CodexMd)"
  }
  Invoke-Skillshare extras init rules-codex --source $Rules --file AGENTS.md --target (Join-Path $env:USERPROFILE '.codex') --as AGENTS.md --mode copy --force --no-tui
  Invoke-Skillshare sync extras
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
  npm install -g @missing
  if ($LASTEXITCODE -ne 0) { throw "npm install -g $($missing -join ' ') 失敗（exit $LASTEXITCODE）" }
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

Install-Skillshare
Install-Uv
Install-Gh
Install-Gitleaks
Sync-RepoConfig
Initialize-Skillshare
Connect-ClaudeRules
Connect-CodexRules
Connect-Skills
Install-McpPackages
Connect-Mcp
Grant-ClaudePermissions
if ($Fresh) { Clear-OldClaudeRules }
Enable-GitHooks
Test-GitIdentity
