<#
OmniKit 移除：把 install.ps1 對這台電腦做的改動還原，可以重複執行。

1. Claude Code：拿掉 ~/.claude/CLAUDE.md 的受管區塊。檔案因此變空時，有安裝前的備份
   （CLAUDE.md.pre-omnikit）就還原，沒有就刪掉這個空檔。
2. Codex：舊版整份換掉的 ~/.codex/AGENTS.md 回到接上 OmniKit 之前的樣子（有備份就還原）；
   新版的受管區塊交給下一步的 agents.py。
3. agents.py disconnect：拿掉 OmniKit 的 skills（連結與複製品）與 MCP server（三邊都是），
   原地拿掉 ~/.codex/AGENTS.md 與 ~/.gemini/GEMINI.md 的受管區塊（只剩區塊就還原安裝前的備份），
   清掉舊版 skillshare 設定裡 OmniKit 的部分，刪掉 agents.json。
   同名但不是 OmniKit 的 skill 與 MCP server 不碰；OmniKit 寫入之後被使用者改過的 MCP server 也留著。
4. 刪掉 %LOCALAPPDATA%\omnikit 裡接好的規則（rules\AGENTS.md）、profile 選擇（profile.json）、
   版本（edition.json）與免問核准的同意紀錄（consent.json）。
5. 權限與提醒 hook：從 ~/.claude/settings.json 拿掉安裝紀錄裡、由 OmniKit 加的規則與 Stop hook；
   從 ~/.codex/config.toml 拿掉 OmniKit 加的 Stop hook。
6. git hook：這個 repo 不再使用 .githooks。
7. 沒加 -KeepTools 時：移除安裝紀錄裡、由 OmniKit 裝的 npm 套件與工具（uv、gh、gitleaks；
   舊版裝的 skillshare 與它的設定資料夾也在紀錄裡的話一併移除）。

只動安裝紀錄（%LOCALAPPDATA%\omnikit\install-record.json）與 agents.json 裡記下的東西；
安裝前就有的工具、套件與權限規則都保留。repo 資料夾本身不刪。

參數：
  -Yes        不詢問，直接移除
  -KeepTools  保留工具與 npm 套件，只還原設定

用法（Windows PowerShell 5.1 或 PowerShell 7）：
  powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\uninstall.ps1 [-Yes] [-KeepTools]
#>
param([switch]$Yes, [switch]$KeepTools)

$ErrorActionPreference = 'Stop'

$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$AgentsPy = Join-Path $Repo 'engine\scripts\agents.py'
$UvExe = Join-Path $env:LOCALAPPDATA 'Programs\uv\uv.exe'
$ProgramsDir = Join-Path $env:LOCALAPPDATA 'Programs'
$SkillshareDir = Join-Path $env:APPDATA 'skillshare'
$SkillshareConfig = Join-Path $SkillshareDir 'config.yaml'
$ClaudeMd = Join-Path $env:USERPROFILE '.claude\CLAUDE.md'
$CodexMd = Join-Path $env:USERPROFILE '.codex\AGENTS.md'
$GeminiMd = Join-Path $env:USERPROFILE '.gemini\GEMINI.md'
$RecordFile = Join-Path $env:LOCALAPPDATA 'omnikit\install-record.json'
$AgentsFile = Join-Path $env:LOCALAPPDATA 'omnikit\agents.json'
# profiles.py 產生的：底線 + profile 接成一份的規則（比對 Codex 用）與這台選的 profile
$ComposedRules = Join-Path $env:LOCALAPPDATA 'omnikit\rules'
$ProfileFile = Join-Path $env:LOCALAPPDATA 'omnikit\profile.json'
# edition.py 記的：這台是哪一版，以及免問核准的同意
$EditionFile = Join-Path $env:LOCALAPPDATA 'omnikit\edition.json'
$ConsentFile = Join-Path $env:LOCALAPPDATA 'omnikit\consent.json'
$BlockPattern = '(?s)<!-- omnikit:rules:begin -->.*?<!-- omnikit:rules:end -->\r?\n?'
$OursHeader = '<!-- 由 OmniKit 產生，不要手改：'
$Utf8 = New-Object Text.UTF8Encoding($false)

function Read-Text($path) { [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8) }

function Get-Uv {
  $onPath = (Get-Command uv -ErrorAction SilentlyContinue).Source
  if ($onPath) { return $onPath }
  if (Test-Path $UvExe) { return $UvExe }
  return $null
}

function Get-FileText($path) { if (Test-Path $path) { Read-Text $path } else { '' } }

# 紀錄壞掉也不會刪到別的東西：只刪 %LOCALAPPDATA%\Programs 底下的資料夾，或 skillshare 的設定資料夾
function Test-Deletable($path) {
  $full = [IO.Path]::GetFullPath($path).TrimEnd('\')
  if ($full -ieq $SkillshareDir) { return $true }
  $parent = Split-Path $full
  return $parent -ieq $ProgramsDir
}

# ---- 讀現況，列出要做的事 ----

$record = @{}
$hasRecord = Test-Path $RecordFile
if ($hasRecord) {
  foreach ($p in (Read-Text $RecordFile | ConvertFrom-Json).PSObject.Properties) { $record[$p.Name] = @($p.Value) }
}
$ssText = Get-FileText $SkillshareConfig
$legacyCodex = $ssText -match '(?m)^\s*- name: rules-codex\s*$'
$legacySkillshare = $legacyCodex -or ($ssText -match '(?m)^  mcp: .*servers\.yaml') -or
  (Test-Path (Join-Path $SkillshareDir 'skills\_omnikit'))
$claudeHasBlock = (Get-FileText $ClaudeMd) -match $BlockPattern
$codexHasBlock = (Get-FileText $CodexMd) -match $BlockPattern
# 舊版整份換掉的格式；新版用受管區塊，交給 agents.py disconnect
$codexOurs = -not $codexHasBlock -and ((Get-FileText $CodexMd).TrimStart().StartsWith($OursHeader) -or $legacyCodex)
$geminiHasBlock = (Get-FileText $GeminiMd) -match $BlockPattern
$hasAgents = (Test-Path $AgentsFile) -or $legacySkillshare
$hasEditionState = (Test-Path $EditionFile) -or (Test-Path $ConsentFile)
$hooksOn = (git -C $Repo config --get core.hooksPath) -eq '.githooks'
$npmPackages = @($record['npm'] | Where-Object { $_ })
$paths = @($record['paths'] | Where-Object { $_ -and (Test-Path $_) })

$plan = @()
if ($claudeHasBlock) { $plan += '拿掉 ~/.claude/CLAUDE.md 的 OmniKit 區塊' }
if ($codexHasBlock) {
  $plan += '拿掉 ~/.codex/AGENTS.md 的 OmniKit 區塊，原本的規則留著（只剩區塊就還原安裝前的備份）'
} elseif ($codexOurs -or (Test-Path "$CodexMd.pre-omnikit")) {
  $plan += '把 ~/.codex/AGENTS.md 還原成接上 OmniKit 之前的樣子'
}
if ($hasAgents) { $plan += '移除 OmniKit 的 skills 與 MCP server（Claude Code、Codex、Antigravity；不是 OmniKit 的、你改過的不碰）' }
if ($geminiHasBlock) { $plan += '拿掉 ~/.gemini/GEMINI.md 的 OmniKit 區塊（原地改寫，硬連結不會斷）' }
if ($legacySkillshare) { $plan += '拿掉舊版 skillshare 設定裡 OmniKit 的部分' }
if ((Test-Path $ComposedRules) -or (Test-Path $ProfileFile) -or $hasEditionState) {
  $plan += '刪除接好的規則、profile 選擇、版本與免問核准的同意紀錄（%LOCALAPPDATA%\omnikit）'
}
if ($record['claude_allow']) { $plan += "從 ~/.claude/settings.json 拿掉權限規則：$($record['claude_allow'] -join ', ')" }
if ($record['claude_hooks']) { $plan += '從 ~/.claude/settings.json 拿掉開新對話提醒 hook' }
if ($record['codex_hooks']) { $plan += '從 ~/.codex/config.toml 拿掉開新對話提醒 hook' }
if ($hooksOn) { $plan += '這個 repo 不再使用 .githooks' }
if (-not $KeepTools) {
  if ($npmPackages) { $plan += "移除 npm 全域套件：$($npmPackages -join ', ')" }
  foreach ($p in $paths) { $plan += "刪除資料夾：$p" }
  if ($paths -contains (Split-Path $UvExe)) { $plan += '清掉 uv 的快取' }
}

if (-not $plan) {
  Write-Host 'OmniKit 沒有接在這台電腦上，不用移除。'
  return
}

Write-Host '將會：'
$plan | ForEach-Object { Write-Host "  - $_" }
if (-not $hasRecord) {
  Write-Warning '找不到安裝紀錄：工具、npm 套件與權限規則無法確定是不是 OmniKit 裝的，全部保留。'
}

# 沒有人能回答時 Read-Host 會拿到 $null，而 $null -notmatch 'y' 是 false；所以非互動一律拒絕，
# 互動時也要明確回答 y 才繼續
if (-not $Yes) {
  if ([Console]::IsInputRedirected) { throw '沒有辦法詢問（非互動模式）；確定要移除的話，加上 -Yes 再執行。' }
  $answer = Read-Host '確定要移除嗎？(y/N)'
  if (-not ("$answer".Trim() -match '^[yY]$')) {
    Write-Host '已取消，什麼都沒改。'
    return
  }
}

# ---- 開始移除 ----

function Remove-ClaudeRules {
  if (-not $claudeHasBlock) { return }
  $rest = [regex]::Replace((Read-Text $ClaudeMd), $BlockPattern, '')
  $backup = "$ClaudeMd.pre-omnikit"
  if ($rest.Trim()) {
    [IO.File]::WriteAllText($ClaudeMd, $rest, $Utf8)
    Write-Host '已拿掉 CLAUDE.md 的 OmniKit 區塊'
    if (Test-Path $backup) { Write-Host "  安裝前的備份還在：$backup，需要的話自己合併回去" }
  } elseif (Test-Path $backup) {
    # -Fresh 是在加上受管區塊之後才備份的，還原時一併拿掉
    [IO.File]::WriteAllText($ClaudeMd, [regex]::Replace((Read-Text $backup), $BlockPattern, ''), $Utf8)
    Remove-Item $backup
    Write-Host '已還原安裝前的 CLAUDE.md'
  } else {
    Remove-Item $ClaudeMd
    Write-Host '已刪除只剩 OmniKit 區塊的 CLAUDE.md'
  }
}

# 舊版整份換掉的格式：有備份就還原；沒有備份、而且檔案是 OmniKit 的副本，就刪掉。
# 新版的受管區塊交給 agents.py disconnect（Disconnect-Agents）
function Remove-CodexRules {
  if ($codexHasBlock) { return }
  if (-not ($codexOurs -or (Test-Path "$CodexMd.pre-omnikit"))) { return }
  $backup = "$CodexMd.pre-omnikit"
  $ours = Join-Path $ComposedRules 'AGENTS.md'
  $isOurCopy = (Test-Path $CodexMd) -and ($codexOurs -or ((Test-Path $ours) -and
    ((Get-FileHash $CodexMd).Hash -eq (Get-FileHash $ours).Hash)))
  if (Test-Path $backup) {
    if (-not (Test-Path $CodexMd) -or $isOurCopy) {
      Move-Item -Force $backup $CodexMd
    } elseif ((Get-FileHash $CodexMd).Hash -eq (Get-FileHash $backup).Hash) {
      Remove-Item $backup
    } else {
      Write-Host "  ~/.codex/AGENTS.md 已經被改過，安裝前的備份留在：$backup"
    }
  } elseif ($isOurCopy) {
    Remove-Item $CodexMd
  }
  Write-Host '已還原 Codex 規則'
}

# skills、MCP、Codex 與 Antigravity 的規則區塊、舊版 skillshare 設定交給 agents.py；它也會刪掉 agents.json
function Disconnect-Agents {
  if (-not ($hasAgents -or $geminiHasBlock -or $codexHasBlock)) { return }
  $uv = Get-Uv
  if (-not $uv) {
    Write-Warning '找不到 uv，OmniKit 的 skills、MCP server 與 ~/.codex/AGENTS.md、~/.gemini/GEMINI.md 的區塊沒有移除；裝好 uv 再重跑'
    return
  }
  & $uv run --quiet $AgentsPy disconnect
  if ($LASTEXITCODE -ne 0) { throw "agents.py disconnect 失敗（exit $LASTEXITCODE）" }
}

# 要在 Remove-CodexRules 之後：它拿接好的規則比對 ~/.codex/AGENTS.md 有沒有被改過
function Remove-ProfileState {
  if (-not ((Test-Path $ComposedRules) -or (Test-Path $ProfileFile) -or $hasEditionState)) { return }
  Remove-Item -Recurse -Force $ComposedRules -ErrorAction SilentlyContinue
  Remove-Item -Force $ProfileFile, $EditionFile, $ConsentFile -ErrorAction SilentlyContinue
  Write-Host '已刪除接好的規則、profile 選擇、版本與免問核准的同意紀錄'
}

function Remove-ClaudePermissions {
  if (-not ($record['claude_allow'] -or $record['claude_hooks'])) { return }
  $uv = Get-Uv
  if (-not $uv) {
    Write-Warning "找不到 uv，請自己從 ~/.claude/settings.json 拿掉：$($record['claude_allow'] -join ', ') 與 hooks.Stop 裡的 session_nudge.py"
    return
  }
  & $uv run --quiet (Join-Path $Repo 'engine\scripts\claude_allow.py') --uninstall
  if ($LASTEXITCODE -ne 0) { throw "claude_allow.py --uninstall 失敗（exit $LASTEXITCODE）" }
}

function Remove-CodexHook {
  if (-not $record['codex_hooks']) { return }
  $uv = Get-Uv
  if (-not $uv) {
    Write-Warning '找不到 uv，請自己從 ~/.codex/config.toml 拿掉 OmniKit 加的 [[hooks.Stop]]（session_nudge.py）'
    return
  }
  & $uv run --quiet (Join-Path $Repo 'engine\scripts\codex_hooks.py') --uninstall
  if ($LASTEXITCODE -ne 0) { throw "codex_hooks.py --uninstall 失敗（exit $LASTEXITCODE）" }
}

function Disable-GitHooks {
  if (-not $hooksOn) { return }
  git -C $Repo config --unset core.hooksPath
  Write-Host '這個 repo 已不再使用 .githooks'
}

function Remove-NpmPackages {
  if (-not $npmPackages) { return }
  if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Warning "找不到 npm，請自己移除：$($npmPackages -join ', ')"
    return
  }
  npm uninstall -g @npmPackages
  if ($LASTEXITCODE -ne 0) { throw "npm uninstall -g $($npmPackages -join ' ') 失敗（exit $LASTEXITCODE）" }
  Write-Host "已移除 npm 套件：$($npmPackages -join ', ')"
}

# 工具本身之外，它們自己留下的東西：舊版 skillshare 在各 target 的空 manifest、uv 的快取、gh 的狀態資料夾。
# 只在該工具是 OmniKit 裝的時候清
function Remove-ToolLeftovers {
  if ($paths -contains $SkillshareDir) {
    $targets = [regex]::Matches((Get-FileText $SkillshareConfig), '(?m)^\s+(?:- )?path: (.+?)\s*$') | ForEach-Object { $_.Groups[1].Value }
    foreach ($dir in $targets) {
      $manifest = Join-Path $dir '.skillshare-manifest.json'
      if (-not (Test-Path $manifest)) { continue }
      if (@((Read-Text $manifest | ConvertFrom-Json).managed.PSObject.Properties).Count -eq 0) { Remove-Item $manifest }
    }
  }
  # uv cache clean 會留下一個空的 .lock，所以清完再把快取資料夾整個刪掉
  if ($paths -contains (Split-Path $UvExe)) {
    $cacheDir = & $UvExe cache dir
    & $UvExe cache clean | Out-Null
    Remove-Item -Recurse -Force $cacheDir -ErrorAction SilentlyContinue
    $uvData = Split-Path $cacheDir
    if ((Test-Path $uvData) -and -not (Get-ChildItem -Force $uvData)) { Remove-Item $uvData }
  }
  if ($paths -contains (Join-Path $ProgramsDir 'gh')) {
    Remove-Item -Recurse -Force (Join-Path $env:LOCALAPPDATA 'GitHub CLI') -ErrorAction SilentlyContinue
    $ghConfig = Join-Path $env:APPDATA 'GitHub CLI'
    if (Test-Path $ghConfig) { Write-Host "  gh 的登入設定留在 $ghConfig，不需要的話可以自己刪" }
  }
}

function Remove-RecordedPaths {
  foreach ($p in $paths) {
    if (-not (Test-Deletable $p)) {
      Write-Warning "安裝紀錄裡的 $p 不在 OmniKit 會安裝的位置，不刪"
      continue
    }
    Remove-Item -Recurse -Force $p
    Write-Host "已刪除 $p"
  }
}

Remove-ClaudeRules
Remove-CodexRules
Disconnect-Agents
Remove-ProfileState
Remove-ClaudePermissions
Remove-CodexHook
Disable-GitHooks
if (-not $KeepTools) {
  Remove-NpmPackages
  Remove-ToolLeftovers
  Remove-RecordedPaths
  if ($hasRecord) {
    Remove-Item -Force $RecordFile
    $recordDir = Split-Path $RecordFile
    if (-not (Get-ChildItem -Force $recordDir)) { Remove-Item $recordDir }
  }
}

Write-Host ''
Write-Host 'OmniKit 已從這台電腦移除。重新開啟 Claude Code、Codex 與 Antigravity 讓設定生效。'
Write-Host "repo 資料夾沒有刪：$Repo"
