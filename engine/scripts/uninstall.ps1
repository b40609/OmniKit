<#
OmniKit 移除：把 install.ps1 對這台電腦做的改動還原，可以重複執行。

1. Claude Code：拿掉 ~/.claude/CLAUDE.md 的受管區塊。檔案因此變空時，有安裝前的備份
   （CLAUDE.md.pre-omnikit）就還原，沒有就刪掉這個空檔。
2. Codex：舊版整份換掉的 ~/.codex/AGENTS.md 回到接上 OmniKit 之前的樣子（有備份就還原）；
   新版的受管區塊交給下一步的 sync.py。
3. sync.py disconnect：拿掉 OmniKit 的 skills 連結、鏡像連結、薄 plugin 與 MCP server（三邊都是，其他設定目錄也是），
   原地拿掉 ~/.codex/AGENTS.md、~/.gemini/AGENTS.md、~/.gemini/GEMINI.md 與其他設定目錄的受管區塊（只剩區塊就還原安裝前的備份），
   T3 Code 的 Antigravity 實例：還指到 OmniKit 轉接程式的 Binary path 拿掉（回到 T3 自動選），
   刪掉 ~/.omnikit/acp 裡的轉接程式；刪掉 config.json（及舊 agents.json）。
   同名但不是 OmniKit 的 skill 與 MCP server 不碰。
4. 刪掉 ~/.omnikit 裡接好的規則（rules\AGENTS.md）、乾淨參照副本（current）、本地薄 plugin 來源（claude-marketplace）、
   profile 選擇（profile.json）、版本（edition.json）與免問核准的同意紀錄（consent.json）。
5. 權限與 hook：從 ~/.claude/settings.json（與其他 Claude 設定目錄的）拿掉安裝紀錄裡、由 OmniKit 加的規則、
   Stop hook 與 SessionStart hook；
   從 ~/.codex/config.toml 拿掉 OmniKit 加的 Stop hook。
6. git hook：這個 repo 不再使用 .githooks。
7. 沒加 -KeepTools 時：移除安裝紀錄裡、由 OmniKit 裝的 npm 套件與工具（uv、gh、gitleaks；
   舊版裝的 skillshare 與它的設定資料夾也在紀錄裡的話一併移除）。

用 uv 跑 Python 腳本時，防毒短暫鎖住 uv 剛建好的暫存執行檔的話，等 3 秒重試一次（engine/scripts/uv-run.ps1，FR-34）。

只動安裝紀錄（~/.omnikit/install-record.json）與 agents.json 裡記下的東西；
安裝前就有的工具、套件與權限規則都保留。repo 資料夾本身不刪。
訪談產生的 profile（~/.omnikit/profiles）是你的個人資料，也不刪：重新安裝就能接著用，
不需要的話自己刪掉。

狀態在 ~/.omnikit（engine/scripts/statedir.py）。舊版放在 %LOCALAPPDATA%\omnikit，從 Claude 桌面版這類封裝的 app
裡跑過的還會有一份被轉存的副本（%LOCALAPPDATA%\Packages\<套件>\LocalCache\Local\omnikit）；一開始先用 statedir.py
把它們合併進 ~/.omnikit，從終端機跑也找得到完整的安裝紀錄。找不到 uv 時直接讀那些位置的安裝紀錄，合在一起用。

參數：
  -Yes        不詢問，直接移除
  -KeepTools  保留工具與 npm 套件，只還原設定

用法（Windows PowerShell 5.1 或 PowerShell 7）：
  powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\uninstall.ps1 [-Yes] [-KeepTools]
#>
param([switch]$Yes, [switch]$KeepTools)

$ErrorActionPreference = 'Stop'

$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$AgentsPy = Join-Path $Repo 'engine\scripts\sync.py'
$UvExe = Join-Path $env:LOCALAPPDATA 'Programs\uv\uv.exe'
$ProgramsDir = Join-Path $env:LOCALAPPDATA 'Programs'
$SkillshareDir = Join-Path $env:APPDATA 'skillshare'
$SkillshareConfig = Join-Path $SkillshareDir 'config.yaml'
$ClaudeMd = Join-Path $env:USERPROFILE '.claude\CLAUDE.md'
$CodexMd = Join-Path $env:USERPROFILE '.codex\AGENTS.md'
$GeminiMd = Join-Path $env:USERPROFILE '.gemini\GEMINI.md'
# 狀態資料夾：跟 statedir.py 一樣是 ~/.omnikit（OMNIKIT_STATE_DIR 可以改）
$StateDir = if ($env:OMNIKIT_STATE_DIR) { $env:OMNIKIT_STATE_DIR } else { Join-Path $env:USERPROFILE '.omnikit' }
$StatedirPy = Join-Path $Repo 'engine\scripts\statedir.py'
$RecordFile = Join-Path $StateDir 'install-record.json'
$AgentsFile = Join-Path $StateDir 'agents.json'
$ConfigFile = Join-Path $StateDir 'config.json'
# profiles.py 產生的：底線 + profile 接成一份的規則（比對 Codex 用）與這台選的 profile
$ComposedRules = Join-Path $StateDir 'rules'
$CurrentClone = Join-Path $StateDir 'current'
$ClaudeMarketplace = Join-Path $StateDir 'claude-marketplace'
$ProfileFile = Join-Path $StateDir 'profile.json'
$OnboardingFile = Join-Path $StateDir 'onboarding.json'
$KitFile = Join-Path $StateDir 'kit.yaml'
$AppliedStateDir = Join-Path $StateDir 'state'
$LocksDir = Join-Path $StateDir 'locks'
$CockpitDir = Join-Path $StateDir 'cockpit'
$CockpitPy = Join-Path $Repo 'scripts\cockpit.py'
$PanelShortcut = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\OmniKit 控制面板.lnk'
$AutostartShortcut = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\OmniKit Cockpit 自動啟動.lnk'
# edition.py 記的：這台是哪一版，以及免問核准的同意
$EditionFile = Join-Path $StateDir 'edition.json'
$ConsentFile = Join-Path $StateDir 'consent.json'
# 訪談產生的 profile：個人資料，不刪（FR-38）
$LocalProfiles = Join-Path $StateDir 'profiles'
$BlockPattern = '(?s)<!-- omnikit:rules:begin -->.*?<!-- omnikit:rules:end -->\r?\n?'
$OursHeader = '<!-- 由 OmniKit 產生，不要手改：'
$Utf8 = New-Object Text.UTF8Encoding($false)

# Invoke-UvRun：跑 uv，防毒短暫鎖住 uv 的暫存執行檔時等一下重試一次（FR-34）
. (Join-Path $PSScriptRoot 'uv-run.ps1')

function Read-Text($path) { [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8) }

# 只找執行檔：Invoke-UvRun 直接啟動它，不經過 PowerShell
function Get-Uv {
  $onPath = (Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
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

# 舊版的狀態位置還有東西的（跟 statedir.py 的 candidates 一樣）
function Get-LegacyStateDirs {
  $dirs = @(Join-Path $env:LOCALAPPDATA 'omnikit')
  $pkgs = Join-Path $env:LOCALAPPDATA 'Packages'
  if (Test-Path -LiteralPath $pkgs) {
    $dirs += @(Get-ChildItem -LiteralPath $pkgs -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName 'LocalCache\Local\omnikit' })
  }
  return @($dirs | Where-Object { (Test-Path -LiteralPath $_) -and @(Get-ChildItem -LiteralPath $_ -Force -ErrorAction SilentlyContinue).Count })
}

# 安裝紀錄：~/.omnikit 的，加上還沒合併的舊位置的（陣列取聯集，其他取第一個有的）
function Read-InstallRecord($files) {
  $merged = @{}
  foreach ($f in $files) {
    if (-not (Test-Path -LiteralPath $f)) { continue }
    try { $json = Read-Text $f | ConvertFrom-Json } catch { Write-Warning "安裝紀錄讀不懂，略過：$f"; continue }
    foreach ($p in $json.PSObject.Properties) {
      $values = @($p.Value)
      if (-not $merged.ContainsKey($p.Name)) { $merged[$p.Name] = $values; continue }
      if (@($values | Where-Object { $_ -is [string] }).Count -eq $values.Count) {
        $merged[$p.Name] = @(@($merged[$p.Name]) + $values | Where-Object { $_ } | Select-Object -Unique)
      }
    }
  }
  return $merged
}

# ---- 先把舊位置的狀態合併進 ~/.omnikit，再讀現況，列出要做的事 ----

if (@(Get-LegacyStateDirs).Count) {
  $uv = Get-Uv
  if ($uv) {
    $r = Invoke-UvRun $uv @('run', '--quiet', $StatedirPy, 'migrate', '--quiet')
    if ($r.Code -ne 0) { Write-Warning "statedir.py migrate 失敗（exit $($r.Code)），改成直接讀舊位置的安裝紀錄" }
  }
}
$recordFiles = @($RecordFile) + @(Get-LegacyStateDirs | ForEach-Object { Join-Path $_ 'install-record.json' })
$record = Read-InstallRecord $recordFiles
$hasRecord = [bool]@($recordFiles | Where-Object { Test-Path -LiteralPath $_ }).Count
$ssText = Get-FileText $SkillshareConfig
$legacyCodex = $ssText -match '(?m)^\s*- name: rules-codex\s*$'
$legacySkillshare = $legacyCodex -or ($ssText -match '(?m)^  mcp: .*servers\.yaml') -or
  (Test-Path (Join-Path $SkillshareDir 'skills\_omnikit'))
$claudeHasBlock = (Get-FileText $ClaudeMd) -match $BlockPattern
$codexHasBlock = (Get-FileText $CodexMd) -match $BlockPattern
# 舊版整份換掉的格式；新版用受管區塊，交給 sync.py disconnect
$codexOurs = -not $codexHasBlock -and ((Get-FileText $CodexMd).TrimStart().StartsWith($OursHeader) -or $legacyCodex)
$geminiHasBlock = (Get-FileText $GeminiMd) -match $BlockPattern
$hasAgents = (Test-Path $ConfigFile) -or (Test-Path $AgentsFile) -or $legacySkillshare
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
if ((Test-Path $ComposedRules) -or (Test-Path $ProfileFile) -or (Test-Path $OnboardingFile) -or (Test-Path $KitFile) -or (Test-Path $CockpitDir) -or $hasEditionState) {
  $plan += "停止本機控制面板並刪除接好的規則、工作台狀態檔（kit.yaml）、profile 選擇與破冰暫緩紀錄、版本與同意紀錄（$StateDir；保留專案設定 cockpit/config.json）"
}
if ((Test-Path -LiteralPath $PanelShortcut) -or (Test-Path -LiteralPath $AutostartShortcut) -or $record['shortcuts']) {
  $plan += '移除開始功能表與登入自啟的控制面板捷徑'
}
if ($record['claude_allow']) { $plan += "從 ~/.claude/settings.json 拿掉權限規則：$($record['claude_allow'] -join ', ')" }
if ($record['claude_hooks']) { $plan += '從 ~/.claude/settings.json 拿掉 OmniKit 的 hook（開新對話提醒、說做不到查證、設定目錄檢查）' }
if ($record['claude_statusline']) { $plan += '從 ~/.claude/settings.json 還原或移除 OmniKit 的狀態列設定（statusLine）' }
if ($record['claude_extra']) { $plan += "其他 Claude 設定目錄的 settings.json 也拿掉 OmniKit 加的權限規則、hook 與狀態列：$(@($record['claude_extra'][0].PSObject.Properties.Name) -join '、')" }
if ($record['codex_hooks']) { $plan += '從 ~/.codex/config.toml 拿掉 OmniKit 的 hook（開新對話提醒、說做不到查證、T3 MCP 斷線防護）' }
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
if (Test-Path -LiteralPath $LocalProfiles) { Write-Host "  （你的 profile 不會刪：$LocalProfiles）" }
$legacyBackup = Join-Path $StateDir 'legacy'
if (Test-Path -LiteralPath $legacyBackup) { Write-Host "  （舊位置搬過來時的備份不會刪：$legacyBackup，不需要的話自己刪）" }
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
# 新版的受管區塊交給 sync.py disconnect（Disconnect-Agents）
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

# skills、MCP、Codex 與 Antigravity 的規則區塊交給 sync.py；它也會刪掉 config.json / agents.json
function Disconnect-Agents {
  if (-not ($hasAgents -or $geminiHasBlock -or $codexHasBlock)) { return }
  $uv = Get-Uv
  if (-not $uv) {
    Write-Warning '找不到 uv，OmniKit 的 skills、MCP server 與 ~/.codex/AGENTS.md、~/.gemini/GEMINI.md 的區塊沒有移除；裝好 uv 再重跑'
    return
  }
  $r = Invoke-UvRun $uv @('run', '--quiet', $AgentsPy, 'disconnect')
  if ($r.Code -ne 0) { throw "sync.py disconnect 失敗（exit $($r.Code)）" }
}

# 要在 Remove-CodexRules 之後：它拿接好的規則比對 ~/.codex/AGENTS.md 有沒有被改過
function Stop-CockpitAndShortcuts {
  $uv = Get-Uv
  if ($uv -and (Test-Path -LiteralPath $CockpitPy)) {
    try {
      $rStop = Invoke-UvRun $uv @('run', '--quiet', $CockpitPy, '--state-dir', $StateDir, 'stop') -Capture
      if ($rStop.Code -ne 0) {
        Write-Warning "停止本機控制面板伺服器回傳非 0（exit $($rStop.Code)）：$($rStop.Output) $($rStop.Error)"
      }
    } catch {
      Write-Warning "停止本機控制面板伺服器時發生例外：$_"
    }
  }
  foreach ($lnk in @($PanelShortcut, $AutostartShortcut) + @($record['shortcuts'] | Where-Object { $_ })) {
    if ($lnk -and (Test-Path -LiteralPath $lnk)) {
      Remove-Item -Force -LiteralPath $lnk -ErrorAction SilentlyContinue
    }
  }
}

function Remove-ProfileState {
  if (-not ((Test-Path $ComposedRules) -or (Test-Path $CurrentClone) -or (Test-Path $ClaudeMarketplace) -or (Test-Path $ProfileFile) -or (Test-Path $OnboardingFile) -or (Test-Path $KitFile) -or (Test-Path $AppliedStateDir) -or (Test-Path $CockpitDir) -or $hasEditionState)) { return }
  if (Test-Path -LiteralPath $CurrentClone) {
    $item = Get-Item -LiteralPath $CurrentClone -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
      [IO.Directory]::Delete($item.FullName)
    } else {
      Remove-Item -Recurse -Force -LiteralPath $CurrentClone -ErrorAction SilentlyContinue
    }
  }
  Remove-Item -Recurse -Force $ComposedRules, $ClaudeMarketplace, $AppliedStateDir, $LocksDir -ErrorAction SilentlyContinue
  if (Test-Path -LiteralPath $CockpitDir) {
    foreach ($runtimeName in @('server.json', 'snapshot.json', 'launch-on-demand.ps1', 'autostart-cockpit.ps1', 'server.log', 'server.err.log')) {
      $rtPath = Join-Path $CockpitDir $runtimeName
      if (Test-Path -LiteralPath $rtPath) { Remove-Item -Force -LiteralPath $rtPath -ErrorAction SilentlyContinue }
    }
    if (-not @(Get-ChildItem -LiteralPath $CockpitDir -Force -ErrorAction SilentlyContinue).Count) {
      Remove-Item -Force -LiteralPath $CockpitDir -ErrorAction SilentlyContinue
    }
  }
  Remove-Item -Force $ProfileFile, $OnboardingFile, $KitFile, $EditionFile, $ConsentFile -ErrorAction SilentlyContinue
  Write-Host '已刪除接好的規則、乾淨參照副本、工作台設定檔、profile 選擇與破冰暫緩紀錄、版本與免問核准同意紀錄（保留個人專案登記與狀態板）'
}

function Remove-ClaudePermissions {
  if (-not ($record['claude_allow'] -or $record['claude_hooks'] -or $record['claude_statusline'] -or $record['claude_extra'])) { return }
  $uv = Get-Uv
  if (-not $uv) {
    Write-Warning "找不到 uv，請自己從 ~/.claude/settings.json 拿掉：$($record['claude_allow'] -join ', ')、hooks.Stop 裡的 session_nudge.py、claim_check.py、done_check.py、hooks.SubagentStop 裡的 done_check.py 與 hooks.SessionStart 裡的 home_watch.py"
    return
  }
  $r = Invoke-UvRun $uv @('run', '--quiet', (Join-Path $Repo 'engine\scripts\claude_allow.py'), '--uninstall')
  if ($r.Code -ne 0) { throw "claude_allow.py --uninstall 失敗（exit $($r.Code)）" }
}

function Remove-CodexHook {
  if (-not $record['codex_hooks']) { return }
  $uv = Get-Uv
  if (-not $uv) {
    Write-Warning '找不到 uv，請自己從 ~/.codex/config.toml 拿掉 OmniKit 加的 [[hooks.Stop]]（session_nudge.py、claim_check.py、done_check.py）'
    return
  }
  $r = Invoke-UvRun $uv @('run', '--quiet', (Join-Path $Repo 'engine\scripts\codex_hooks.py'), '--uninstall')
  if ($r.Code -ne 0) { throw "codex_hooks.py --uninstall 失敗（exit $($r.Code)）" }
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

Stop-CockpitAndShortcuts
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
if (Test-Path -LiteralPath $LocalProfiles) { Write-Host "你的 profile 沒有刪：$LocalProfiles（重新安裝就能接著用，不需要的話自己刪掉）" }
