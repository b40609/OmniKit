<#
OmniKit 安裝前檢查（FR-35）：在 install.ps1 下載或寫入任何東西之前，先確認安裝本身需要的條件。
任一項不通過，install.ps1 就不寫入任何設定，並列出處理方式。結果只有項目名稱與通過與否，只印在這台，不上傳。

檢查項目：
  git        有 git（Git for Windows）
  github     連得到 github.com 與 api.github.com（下載 uv、gh 與 skills）
  npm        有 npm，而且連得到 registry.npmjs.org（MCP 用的套件）
  pypi       連得到 pypi.org（uv 安裝 Python 相依套件）
  proxy      Windows 有設 proxy 時，命令列也設了 HTTPS_PROXY：git、npm、uv 不會讀 Windows 的 proxy 設定
  antivirus  有已知會攔下下載程式的防毒（Trend Micro）時，uv 已經能執行；讀不到防毒資訊時不擋
  policy     群組原則沒有把 PowerShell 執行原則鎖成 Restricted 或 AllSigned（這時 -ExecutionPolicy Bypass 也沒用）

參數：
  -Json       只輸出 JSON：[{"name": "git", "ok": true}, ...]（doctor.py 用）
  -Skip <名稱> 已經自己處理好、要略過的項目，例如防毒已請 IT 放行：-Skip antivirus
  -SelfTest   用假的偵測結果測判斷規則，不連網、不讀這台的設定（CI 在 Linux 的 pwsh 上也會跑）

結束碼：全部通過（或略過）是 0，有不通過的是 1。
用法：powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\preflight.ps1 [-Json] [-Skip antivirus]
#>
param([switch]$Json, [string[]]$Skip = @(), [switch]$SelfTest)

$ProgressPreference = 'SilentlyContinue'
$KnownBlockers = @('Trend Micro')  # 2026-11：會攔下未簽章的下載程式，允許通知要剛好盯著畫面才按得到
$Labels = [ordered]@{
  git = 'git'; github = '連得到 GitHub'; npm = 'npm'; pypi = '連得到 PyPI'; proxy = 'proxy 設定'
  antivirus = '防毒產品'; policy = 'PowerShell 執行原則'
}
$Fixes = @{
  git       = '安裝 Git for Windows：winget install --id Git.Git -e，裝好後開新的終端機再跑一次'
  github    = '確認網路連得到 https://github.com 與 https://api.github.com；公司網路請設定 proxy（見 proxy 項）或請 IT 放行'
  npm       = '安裝 Node.js LTS：winget install --id OpenJS.NodeJS.LTS -e；已經裝了就確認連得到 https://registry.npmjs.org（npm config set proxy）'
  pypi      = '確認連得到 https://pypi.org；公司網路請設定 HTTPS_PROXY，或請 IT 放行'
  proxy     = 'Windows 有設 proxy，但命令列工具讀不到：把使用者環境變數 HTTPS_PROXY 與 HTTP_PROXY 設成同一個 proxy（git 另外 git config --global http.proxy），開新的終端機再跑'
  antivirus = '防毒可能攔下 OmniKit 下載的程式（uv、gh）。請 IT 把 %LOCALAPPDATA%\Programs 與 OmniKit 資料夾加入例外，或安裝時盯著畫面按允許；處理好後加 -Skip antivirus 重跑'
  policy    = '公司群組原則鎖住了 PowerShell 腳本（Restricted 或 AllSigned），-ExecutionPolicy Bypass 也蓋不過，請 IT 放行 OmniKit 的腳本'
}

function Test-Url($url) {
  try {
    $r = Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing -TimeoutSec 10
    return [int]$r.StatusCode -lt 500
  } catch {
    # 有回應（即使是 4xx）就表示連得到
    $resp = $_.Exception.Response
    if ($resp) { return [int]$resp.StatusCode -lt 500 }
    return $false
  }
}

function Get-SystemProxy {
  $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
  $ie = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
  if ($ie -and (($ie.ProxyEnable -eq 1 -and $ie.ProxyServer) -or $ie.AutoConfigURL)) { return $true }
  $winhttp = (netsh winhttp show proxy 2>$null) -join "`n"
  return [bool]($winhttp -match 'Proxy Server\(s\)\s*:\s*\S')
}

function Get-Facts {
  $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
  if (-not $uv) { $uv = Join-Path $env:LOCALAPPDATA 'Programs\uv\uv.exe' }
  $uvRuns = $false
  if (Test-Path $uv) { try { & $uv --version *> $null; $uvRuns = ($LASTEXITCODE -eq 0) } catch { $uvRuns = $false } }
  $products = $null
  try {
    $products = @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction Stop | ForEach-Object { $_.displayName })
  } catch { $products = $null }
  $policies = @{}
  foreach ($scope in 'MachinePolicy', 'UserPolicy') {
    try { $policies[$scope] = [string](Get-ExecutionPolicy -Scope $scope) } catch { $policies[$scope] = 'Undefined' }
  }
  return @{
    git = [bool](Get-Command git -ErrorAction SilentlyContinue)
    github = (Test-Url 'https://api.github.com') -and (Test-Url 'https://github.com')
    npm = [bool](Get-Command npm -ErrorAction SilentlyContinue)
    npmRegistry = Test-Url 'https://registry.npmjs.org/-/ping'
    pypi = Test-Url 'https://pypi.org/simple/pip/'
    systemProxy = Get-SystemProxy
    envProxy = [bool]($env:HTTPS_PROXY -or $env:https_proxy -or $env:HTTP_PROXY -or $env:http_proxy)
    antivirus = $products
    uvRuns = $uvRuns
    policies = $policies
  }
}

# 判斷規則與偵測分開，自我測試只餵假的偵測結果
function Get-Results($facts, $skip) {
  $blocked = @($facts.antivirus | Where-Object { $p = $_; $KnownBlockers | Where-Object { $p -like "*$_*" } })
  $locked = @($facts.policies.Values | Where-Object { $_ -in 'Restricted', 'AllSigned' })
  $ok = [ordered]@{
    git = [bool]$facts.git
    github = [bool]$facts.github
    npm = [bool]($facts.npm -and $facts.npmRegistry)
    pypi = [bool]$facts.pypi
    proxy = (-not $facts.systemProxy) -or [bool]$facts.envProxy
    antivirus = ($null -eq $facts.antivirus) -or ($blocked.Count -eq 0) -or [bool]$facts.uvRuns
    policy = $locked.Count -eq 0
  }
  foreach ($name in @($ok.Keys)) {
    [pscustomobject]@{ name = $name; ok = ($ok[$name] -or ($skip -contains $name)); skipped = ($skip -contains $name -and -not $ok[$name]) }
  }
}

function Show-Results($results) {
  Write-Host '安裝前檢查：'
  foreach ($r in $results) {
    $state = if ($r.skipped) { '略過' } elseif ($r.ok) { '通過' } else { '不通過' }
    Write-Host ("  {0}  {1}" -f $state, $Labels[$r.name])
  }
  $bad = @($results | Where-Object { -not $_.ok })
  if ($bad.Count) {
    Write-Host ''
    Write-Host '處理方式：'
    foreach ($r in $bad) { Write-Host ("  - {0}：{1}" -f $Labels[$r.name], $Fixes[$r.name]) }
  }
}

function ConvertTo-ResultJson($results) {
  # 只有名稱與通過與否
  return ConvertTo-Json -Compress -InputObject @($results | ForEach-Object { [ordered]@{ name = $_.name; ok = [bool]$_.ok } })
}

function Invoke-SelfTest {
  $script:failures = 0
  function Check($label, $cond) {
    if ($cond) { Write-Host "通過：$label" } else { Write-Host "失敗：$label"; $script:failures++ }
  }
  $good = @{ git = $true; github = $true; npm = $true; npmRegistry = $true; pypi = $true; systemProxy = $false; envProxy = $false
             antivirus = @('Windows Defender'); uvRuns = $false; policies = @{ MachinePolicy = 'Undefined'; UserPolicy = 'Undefined' } }
  function With($changes) { $f = $good.Clone(); foreach ($k in $changes.Keys) { $f[$k] = $changes[$k] }; return $f }
  function Failed($facts, $skip = @()) { return @(Get-Results $facts $skip | Where-Object { -not $_.ok } | ForEach-Object { $_.name }) }

  Check '全部正常：七項都通過' ((Failed $good).Count -eq 0 -and @(Get-Results $good @()).Count -eq 7)
  Check '沒有 git：只有 git 不通過' ((Failed (With @{ git = $false })) -join ',' -eq 'git')
  Check '有 npm 但連不到 registry：npm 不通過' ((Failed (With @{ npmRegistry = $false })) -join ',' -eq 'npm')
  Check 'Windows 有 proxy、命令列沒設：proxy 不通過' ((Failed (With @{ systemProxy = $true })) -join ',' -eq 'proxy')
  Check 'Windows 有 proxy、命令列也設了：通過' ((Failed (With @{ systemProxy = $true; envProxy = $true })).Count -eq 0)
  Check 'Trend Micro 在、uv 還不能跑：防毒不通過' ((Failed (With @{ antivirus = @('Trend Micro Apex One') })) -join ',' -eq 'antivirus')
  Check 'Trend Micro 在、uv 已經能跑：通過' ((Failed (With @{ antivirus = @('Trend Micro Apex One'); uvRuns = $true })).Count -eq 0)
  Check '讀不到防毒資訊（例如伺服器版 Windows）：不擋' ((Failed (With @{ antivirus = $null })).Count -eq 0)
  Check '群組原則鎖成 AllSigned：執行原則不通過' ((Failed (With @{ policies = @{ MachinePolicy = 'AllSigned'; UserPolicy = 'Undefined' } })) -join ',' -eq 'policy')
  Check '使用者自己設 RemoteSigned 不算鎖住' ((Failed (With @{ policies = @{ MachinePolicy = 'Undefined'; UserPolicy = 'RemoteSigned' } })).Count -eq 0)
  $skipped = @(Get-Results (With @{ antivirus = @('Trend Micro') }) @('antivirus'))
  Check '-Skip antivirus：算通過並標成略過' (@($skipped | Where-Object { -not $_.ok }).Count -eq 0 -and ($skipped | Where-Object { $_.name -eq 'antivirus' }).skipped)
  $doc = ConvertTo-ResultJson (Get-Results (With @{ git = $false }) @()) | ConvertFrom-Json
  Check 'JSON 只有名稱與通過與否' (@($doc).Count -eq 7 -and (@($doc[0].PSObject.Properties.Name) -join ',') -eq 'name,ok' -and $doc[0].name -eq 'git' -and -not $doc[0].ok)
  Check '每一項都有處理方式' (@($Labels.Keys | Where-Object { -not $Fixes[$_] }).Count -eq 0)

  Write-Host ''
  Write-Host $(if ($script:failures) { "$($script:failures) 項失敗" } else { '全部通過' })
  return $script:failures
}

if ($SelfTest) { exit (Invoke-SelfTest) }

$results = @(Get-Results (Get-Facts) $Skip)
if ($Json) { ConvertTo-ResultJson $results } else { Show-Results $results }
exit $(if (@($results | Where-Object { -not $_.ok }).Count) { 1 } else { 0 })
