<#
uv run 的共用包裝：install.ps1 與 uninstall.ps1 用 . 載入，不直接執行。

防毒（例如 Trend Micro）會短暫鎖住 uv 剛在 TEMP 建好的暫存執行檔（uv-trampoline-*.exe），uv 回報
「Failed to update Windows PE resources」或 os error 32，重跑就過。遇到這類錯誤等 3 秒重試一次，並印一行說明（FR-34）；
其他失敗不重試，結束碼照實回傳，由呼叫的地方決定要不要丟出。

不用 & uv ... 2> 檔案 收 stderr，因為：
- PowerShell 5.1 在 $ErrorActionPreference = 'Stop' 時，轉向原生指令的 stderr 會把第一行當成錯誤丟出。
- PowerShell 用主控台字碼頁（中文 Windows 是 cp950）解讀原生指令的輸出，uv 與 Python 寫的是 UTF-8，中文會變亂碼。
所以用 .NET 的 Process 啟動 uv：stdin 與 stdout 照常接在主控台（訪談與 --ask 的提問看得到、也能回答），
只有 stderr 收進來：逐行先當 UTF-8 解，不是合法的 UTF-8 才用主控台字碼頁解，再原樣印回 stderr。
-Capture 時 stdout 也收起來回傳，只給 --show 這類只印 ASCII 值的指令用。
#>

# uv 的暫存執行檔被鎖住時的訊息（跟 windows-ci.ps1 一樣）
$UvLockedPattern = 'Failed to update Windows PE resources|os error 32\b|being used by another process'
$UvRetrySeconds = 3

# 照 Windows 解析命令列的規則把參數接成一行：有空白、引號或是空字串的加上引號，引號與結尾前的反斜線加倍
function ConvertTo-UvCommandLine([string[]]$arguments) {
  return (@($arguments | ForEach-Object {
        if ($_ -and $_ -notmatch '[\s"]') { $_ } else { '"' + (($_ -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"' }
      }) -join ' ')
}

# 子行程的輸出：逐行先當 UTF-8 解；不是合法的 UTF-8（例如沒設 UTF-8 的 Python 用 cp950 寫）才用 $fallback 解
function ConvertFrom-UvBytes([byte[]]$bytes, [Text.Encoding]$fallback = [Console]::OutputEncoding) {
  $strict = New-Object Text.UTF8Encoding($false, $true)
  $lines = New-Object System.Collections.ArrayList
  $start = 0
  for ($i = 0; $i -le $bytes.Length; $i++) {
    if ($i -eq $bytes.Length -or $bytes[$i] -eq 10) {
      $chunk = New-Object byte[] ($i - $start)
      [Array]::Copy($bytes, $start, $chunk, 0, $chunk.Length)
      try { [void]$lines.Add($strict.GetString($chunk)) } catch { [void]$lines.Add($fallback.GetString($chunk)) }
      $start = $i + 1
    }
  }
  return ($lines -join "`n").Replace("`r", '').TrimEnd("`n")
}

# 執行 uv（$arguments 例如 run --quiet <腳本> ...），回傳 Code（結束碼）、Output（-Capture 時的 stdout）、
# Error（stderr）與 Retried（是不是重試過）。stderr 印回主控台；被防毒鎖住的那一次只印一行說明
function Invoke-UvRun([string]$uv, [string[]]$arguments, [switch]$Capture) {
  # 說明裡只寫腳本檔名與後面的參數，不寫完整路徑
  $i = 0
  while ($i -lt $arguments.Count -and $arguments[$i] -notlike '*.py') { $i++ }
  $label = if ($i -lt $arguments.Count) { (@(Split-Path -Leaf $arguments[$i]) + @($arguments | Select-Object -Skip ($i + 1))) -join ' ' } else { $arguments -join ' ' }
  for ($try = 1; ; $try++) {
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $uv
    $info.Arguments = ConvertTo-UvCommandLine $arguments
    $info.UseShellExecute = $false
    $info.WorkingDirectory = (Get-Location -PSProvider FileSystem).ProviderPath
    $info.RedirectStandardError = $true
    if ($Capture) {
      $info.RedirectStandardOutput = $true
      $info.StandardOutputEncoding = New-Object Text.UTF8Encoding($false)
    }
    $process = [Diagnostics.Process]::Start($info)
    $stderr = New-Object IO.MemoryStream
    $copying = $process.StandardError.BaseStream.CopyToAsync($stderr)
    $stdout = if ($Capture) { $process.StandardOutput.ReadToEnd() } else { '' }
    $process.WaitForExit()
    # uv 結束後還有別的行程開著 stderr 時不要一直等；沒讀完就當成沒有輸出
    $text = if ($copying.Wait(10000)) { ConvertFrom-UvBytes $stderr.ToArray() } else { '' }
    $code = $process.ExitCode
    $process.Dispose()
    if ($code -ne 0 -and $try -eq 1 -and $text -match $UvLockedPattern) {
      Write-Host "uv 的暫存執行檔被鎖住（多半是防毒在掃描），$UvRetrySeconds 秒後重試一次：$label"
      Start-Sleep -Seconds $UvRetrySeconds
      continue
    }
    if ($text) { [Console]::Error.WriteLine($text) }
    if ($code -ne 0 -and $text -match $UvLockedPattern) {
      Write-Host '重試後還是被鎖住：等防毒掃描完（通常幾秒）再重跑一次。'
    }
    return [pscustomobject]@{ Code = $code; Output = $stdout; Error = $text; Retried = ($try -gt 1) }
  }
}
