<#
OmniKit 安裝：把這台 Windows 電腦接上 OmniKit，可以重複執行。

1. 安裝固定版本的 skillshare 與 uv：從 GitHub release 下載 zip，比對寫死的 SHA256 後解壓；
   不改 PATH。這台已經有 uv 就沿用。
2. 第一次執行時初始化 skillshare，target 是 Claude Code 與 Codex。
3. 把 data/rules/AGENTS.md 接到兩邊：Claude 用 import，Codex 用複製，然後同步。
4. 設定 git hook：commit 前驗證名冊；commit 或 pull 動到規則時，自動同步給 Codex。
5. 檢查 OmniKit repo 的 git 身分。

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

$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Rules = Join-Path $Repo 'data\rules'
$Arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
$BinDir = Join-Path $env:LOCALAPPDATA 'Programs\skillshare'
$Exe = Join-Path $BinDir 'skillshare.exe'
$UvDir = Join-Path $env:LOCALAPPDATA 'Programs\uv'
$UvExe = Join-Path $UvDir 'uv.exe'
$ClaudeMd = Join-Path $env:USERPROFILE '.claude\CLAUDE.md'
$BlockPattern = '(?s)<!-- omnikit:rules:begin -->.*?<!-- omnikit:rules:end -->'

function Invoke-Skillshare {
  & $Exe @args
  if ($LASTEXITCODE -ne 0) { throw "skillshare $($args -join ' ') 失敗（exit $LASTEXITCODE）" }
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

# Codex 不支援 import，由 skillshare 複製一份；--force 讓重複執行時覆寫成同一份定義
function Connect-CodexRules {
  Invoke-Skillshare extras init rules-codex --source $Rules --file AGENTS.md --target (Join-Path $env:USERPROFILE '.codex') --as AGENTS.md --mode copy --force --no-tui
  Invoke-Skillshare sync extras
}

# 只留下 OmniKit 的受管區塊；舊內容先備份
function Clear-OldClaudeRules {
  $text = [IO.File]::ReadAllText($ClaudeMd, [Text.Encoding]::UTF8)
  $block = [regex]::Match($text, $BlockPattern).Value
  if ($text.Trim() -eq $block) { return }
  $backup = "$ClaudeMd.pre-omnikit"
  if (Test-Path $backup) { $backup += '-' + (Get-Date -Format 'yyyyMMddHHmmss') }
  Copy-Item $ClaudeMd $backup
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
Initialize-Skillshare
Connect-ClaudeRules
Connect-CodexRules
if ($Fresh) { Clear-OldClaudeRules }
Enable-GitHooks
Test-GitIdentity
