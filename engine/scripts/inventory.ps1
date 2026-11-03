<#
OmniKit 舊環境盤點（唯讀）

換電腦或重建 agent 環境前，列出這台電腦的 Claude Code、Codex 與其他 agent 工具
用過哪些 skills、plugins、MCP、規則與 CLI，當作名冊匯入的參考。

只輸出名稱、使用次數、日期與 Markdown 標題。不輸出金鑰、token、env 的值、MCP 的 args 與 URL，
也不開啟 .credentials.json、auth.json、.env。除了用 git config 讀全域身分，不執行其他程式。

用法（Windows PowerShell 5.1 或 PowerShell 7）：
  powershell -NoProfile -ExecutionPolicy Bypass -File .\inventory.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File .\inventory.ps1 -OutDir D:\tmp

輸出：<OutDir>\omnikit-inventory-<電腦名>-<日期>.md，OutDir 預設為 Downloads。
帶走之前請自己先看一遍。
#>
param([string]$OutDir = (Join-Path $env:USERPROFILE 'Downloads'))

$ErrorActionPreference = 'SilentlyContinue'
$H = $env:USERPROFILE
$lines = New-Object 'System.Collections.Generic.List[string]'

function Add-Line([string]$s = '') { $lines.Add($s) }

# @($null).Count 在 PowerShell 是 1，所以另外處理 $null
function Get-Count($x) { if ($null -eq $x) { 0 } else { @($x).Count } }

function Get-Day($ms) {
  if ($ms) { [DateTimeOffset]::FromUnixTimeMilliseconds([int64]$ms).LocalDateTime.ToString('yyyy-MM-dd') }
}

function Read-Json($path) {
  if (Test-Path $path) {
    try { Get-Content -Raw -Encoding UTF8 $path | ConvertFrom-Json } catch { $null }
  }
}

function Add-Headings($path) {
  if (-not (Test-Path $path)) { Add-Line '- （不存在）'; return }
  if ((Get-Item $path).Length -eq 0) { Add-Line '- （空檔）'; return }
  $hs = @(Select-String -Path $path -Encoding UTF8 -Pattern '^\s{0,3}#{1,3}\s')
  if ($hs.Count -eq 0) { Add-Line '- （沒有標題）'; return }
  foreach ($h in $hs) { Add-Line ('- ' + $h.Line.Trim()) }
}

function Add-Names($dir) {
  if (-not (Test-Path $dir)) { Add-Line '- （不存在）'; return }
  $items = @(Get-ChildItem -Recurse -File $dir)
  if ($items.Count -eq 0) { Add-Line '- （空）'; return }
  foreach ($i in $items) { Add-Line ('- ' + $i.FullName.Substring($dir.Length).TrimStart('\')) }
}

# 列出 skill 目錄名稱與 SKILL.md 的 description（截到 120 字）；略過 . 開頭的內建目錄
function Add-Skills($dir) {
  if (-not (Test-Path $dir)) { Add-Line '- （不存在）'; return }
  $dirs = @(Get-ChildItem -Directory -Force $dir | Where-Object { -not $_.Name.StartsWith('.') })
  if ($dirs.Count -eq 0) { Add-Line '- （空）'; return }
  foreach ($d in $dirs) {
    $desc = ''
    $md = Join-Path $d.FullName 'SKILL.md'
    if (Test-Path $md) {
      $m = Select-String -Path $md -Encoding UTF8 -Pattern '^description:\s*(.+)$' | Select-Object -First 1
      if ($m) {
        $desc = $m.Matches[0].Groups[1].Value.Trim().Trim('"', "'")
        if ($desc.Length -gt 120) { $desc = $desc.Substring(0, 120) + '…' }
      }
    }
    if ($desc) { Add-Line ('- {0}：{1}' -f $d.Name, $desc) } else { Add-Line ('- ' + $d.Name) }
  }
}

function Add-Usage($obj, $title) {
  Add-Line "### $title（依使用次數排序）"
  $props = @()
  if ($obj) { $props = @($obj.PSObject.Properties) }
  if ($props.Count -eq 0) { Add-Line '- （沒有紀錄）'; return }
  $rows = $props | ForEach-Object {
    [pscustomobject]@{ Name = $_.Name; Count = [int]$_.Value.usageCount; Last = (Get-Day $_.Value.lastUsedAt) }
  } | Sort-Object Count -Descending
  foreach ($r in $rows) { Add-Line ('- {0}：{1} 次，最後 {2}' -f $r.Name, $r.Count, $r.Last) }
}

# 只列 MCP 名稱、類型與執行檔名；args、env、url 一律不列。回傳列出的數量
function Add-Mcp($servers, [string]$indent = '') {
  $props = @()
  if ($servers) { $props = @($servers.PSObject.Properties) }
  foreach ($p in $props) {
    $s = $p.Value
    $kind = if ($s.type) { $s.type } elseif ($s.url) { 'http' } else { 'stdio' }
    $exe = if ($s.command) { '，' + (Split-Path -Leaf $s.command) } else { '' }
    Add-Line ('{0}- {1}（{2}{3}）' -f $indent, $p.Name, $kind, $exe)
  }
  return $props.Count
}

Add-Line '# OmniKit 舊環境盤點'
Add-Line
Add-Line ('- 電腦：' + $env:COMPUTERNAME)
Add-Line ('- 時間：' + (Get-Date -Format 'yyyy-MM-dd HH:mm'))
Add-Line ('- PowerShell：' + $PSVersionTable.PSVersion)
$gpu = @(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join '、'
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
Add-Line ('- 硬體：{0}；記憶體 {1} GB' -f $gpu, $ram)
Add-Line ('- git 全域身分：{0} <{1}>' -f (git config --global user.name), (git config --global user.email))
Add-Line

Add-Line '## Claude Code'
Add-Line '### 全域規則標題（~\.claude\CLAUDE.md）'
Add-Headings "$H\.claude\CLAUDE.md"
Add-Line '### rules（~\.claude\rules）'
Add-Names "$H\.claude\rules"
Add-Line '### skills（~\.claude\skills）'
Add-Skills "$H\.claude\skills"
foreach ($d in 'agents', 'commands', 'output-styles') {
  Add-Line "### $d（~\.claude\$d）"
  Add-Names "$H\.claude\$d"
}

Add-Line '### settings.json（只列鍵名）'
$st = Read-Json "$H\.claude\settings.json"
if ($st) {
  Add-Line ('- 頂層鍵：' + (@($st.PSObject.Properties.Name) -join '、'))
  if ($st.enabledPlugins) { Add-Line ('- enabledPlugins：' + (@($st.enabledPlugins.PSObject.Properties.Name) -join '、')) }
  if ($st.hooks) { Add-Line ('- hooks 事件：' + (@($st.hooks.PSObject.Properties.Name) -join '、')) }
  if ($st.permissions) {
    Add-Line ('- permissions：allow {0} 條、deny {1} 條' -f (Get-Count $st.permissions.allow), (Get-Count $st.permissions.deny))
  }
  if ($st.env) { Add-Line ('- env：{0} 個鍵，值不列' -f @($st.env.PSObject.Properties).Count) }
} else { Add-Line '- （不存在或無法解析）' }

Add-Line '### MCP（~\.claude.json；只列名稱、類型與執行檔名）'
$cj = Read-Json "$H\.claude.json"
if ($cj) {
  Add-Line '使用者層：'
  if ((Add-Mcp $cj.mcpServers) -eq 0) { Add-Line '- （沒有）' }
  Add-Line '專案層：'
  $n = 0
  if ($cj.projects) {
    foreach ($p in @($cj.projects.PSObject.Properties)) {
      if ($p.Value.mcpServers -and @($p.Value.mcpServers.PSObject.Properties).Count -gt 0) {
        Add-Line ('- ' + $p.Name)
        $n += Add-Mcp $p.Value.mcpServers '  '
      }
    }
  }
  if ($n -eq 0) { Add-Line '- （沒有）' }
  Add-Usage $cj.skillUsage 'skill 使用紀錄'
  Add-Usage $cj.pluginUsage 'plugin 使用紀錄'
  Add-Line '### 用過 Claude Code 的專案'
  if ($cj.projects) { foreach ($name in @($cj.projects.PSObject.Properties.Name)) { Add-Line ('- ' + $name) } }
} else { Add-Line '- （~\.claude.json 不存在或無法解析）' }

Add-Line '### Claude 桌面版 MCP（%APPDATA%\Claude\claude_desktop_config.json）'
$cd = Read-Json "$env:APPDATA\Claude\claude_desktop_config.json"
$c = 0
if ($cd) { $c = Add-Mcp $cd.mcpServers }
if ($c -eq 0) { Add-Line '- （沒有）' }

Add-Line '### plugins（~\.claude\plugins）'
$pc = 0
foreach ($f in 'installed_plugins.json', 'known_marketplaces.json') {
  $o = Read-Json "$H\.claude\plugins\$f"
  if ($o) {
    $src = if ($o.plugins) { $o.plugins } else { $o }
    Add-Line ('- {0}：{1}' -f $f, (@($src.PSObject.Properties.Name) -join '、'))
    $pc++
  }
}
if ($pc -eq 0) { Add-Line '- （沒有安裝紀錄）' }
Add-Line

Add-Line '## Codex'
Add-Line '### 全域規則標題（~\.codex\AGENTS.md）'
Add-Headings "$H\.codex\AGENTS.md"
Add-Line '### config.toml（只列區段名稱與頂層鍵名，不列值）'
$toml = "$H\.codex\config.toml"
if (Test-Path $toml) {
  $inSection = $false
  foreach ($l in Get-Content -Encoding UTF8 $toml) {
    $t = $l.Trim()
    if ($t -match '^\[\[?[^\]]+\]\]?') { $inSection = $true; Add-Line ('- ' + $Matches[0]) }
    elseif (-not $inSection -and $t -match '^([A-Za-z0-9_.\-]+)\s*=') { Add-Line ('- 頂層鍵：' + $Matches[1]) }
  }
} else { Add-Line '- （不存在）' }
Add-Line '### skills（~\.codex\skills，不含內建 .system）'
Add-Skills "$H\.codex\skills"
Add-Line '### skills（~\.agents\skills）'
Add-Skills "$H\.agents\skills"
foreach ($d in 'prompts', 'agents', 'rules') {
  Add-Line "### $d（~\.codex\$d）"
  Add-Names "$H\.codex\$d"
}
Add-Line '### hooks.json（只列頂層鍵）'
$hj = Read-Json "$H\.codex\hooks.json"
if ($hj) { Add-Line ('- ' + (@($hj.PSObject.Properties.Name) -join '、')) } else { Add-Line '- （不存在）' }
Add-Line '### plugins 快取（~\.codex\plugins\cache）'
$cache = "$H\.codex\plugins\cache"
if (Test-Path $cache) {
  foreach ($mk in @(Get-ChildItem -Directory $cache)) {
    $ps = @(Get-ChildItem -Directory $mk.FullName | Select-Object -ExpandProperty Name) -join '、'
    Add-Line ('- {0}：{1}' -f $mk.Name, $ps)
  }
} else { Add-Line '- （不存在）' }
Add-Line

Add-Line '## 其他 agent 工具的設定目錄（只看存在與否）'
$found = 0
foreach ($o in '.gemini', '.cursor', '.windsurf', '.codeium', '.continue', '.aider', '.kiro', '.qwen', '.opencode', '.config\opencode', '.cline', '.roo', '.workbuddy', '.codebuddy', '.zcode', '.serena', '.bmad') {
  if (Test-Path "$H\$o") { Add-Line ('- ~\' + $o); $found++ }
}
if ($found -eq 0) { Add-Line '- （沒有）' }
Add-Line

Add-Line '## 本地模型（只列名稱）'
$lm = 0
$ol = "$H\.ollama\models\manifests"
if (Test-Path $ol) {
  foreach ($f in @(Get-ChildItem -Recurse -File $ol)) { Add-Line ('- ollama：{0}:{1}' -f $f.Directory.Name, $f.Name); $lm++ }
}
foreach ($root in "$H\.lmstudio\models", "$H\.cache\lm-studio\models") {
  if (Test-Path $root) {
    foreach ($pub in @(Get-ChildItem -Directory $root)) {
      foreach ($m in @(Get-ChildItem -Directory $pub.FullName)) { Add-Line ('- LM Studio：{0}/{1}' -f $pub.Name, $m.Name); $lm++ }
    }
  }
}
if ($lm -eq 0) { Add-Line '- （沒有找到 Ollama 或 LM Studio 的模型）' }
Add-Line

Add-Line '## PATH 上的 CLI（只查路徑，不執行）'
foreach ($c in 'claude', 'codex', 'gemini', 'node', 'npx', 'pnpm', 'bun', 'python', 'py', 'uv', 'uvx', 'git', 'gh', 'docker', 'ollama', 'lms', 'rtk', 'skillshare', 'rulesync', 'gitleaks', 'winget', 'scoop') {
  $cmd = Get-Command $c -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($cmd) { Add-Line ('- {0}：{1}' -f $c, $cmd.Source) } else { Add-Line ('- {0}：（沒有）' -f $c) }
}

# 前面讀取失敗只會少幾列；寫檔失敗則要明確報錯，不能假裝成功
$ErrorActionPreference = 'Stop'
try {
  if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
  $file = Join-Path $OutDir ('omnikit-inventory-{0}-{1}.md' -f $env:COMPUTERNAME, (Get-Date -Format 'yyyyMMdd'))
  $lines | Out-File -FilePath $file -Encoding utf8
} catch {
  Write-Host ('寫檔失敗：' + $_.Exception.Message) -ForegroundColor Red
  exit 1
}
Write-Host ('已寫入：' + $file)
Write-Host '帶走之前請自己先看一遍，確認沒有不想分享的內容。'
