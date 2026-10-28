# Windows PowerShell 5.1 worker chạy sẵn: nạp WinRT và giọng một lần, sau đó đọc từng dòng JSON từ stdin.
# Text là dữ liệu JSON, không bao giờ là mã PowerShell. Không ghi tệp hay registry.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Send($Object) {
    [Console]::Out.WriteLine(($Object | ConvertTo-Json -Compress))
    [Console]::Out.Flush()
}

function Test-Vietnamese([string]$Language) {
    return $Language.ToLowerInvariant().Replace('_', '-') -in @('vi', 'vi-vn')
}

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType=WindowsRuntime]
    $streamType = [Windows.Media.SpeechSynthesis.SpeechSynthesisStream, Windows.Media.SpeechSynthesis, ContentType=WindowsRuntime]
    $asTask = @([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetGenericArguments().Count -eq 1 -and
        $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0].MakeGenericMethod($streamType)
    $init = [Console]::In.ReadLine() | ConvertFrom-Json
    $voices = @([Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object {
        (Test-Vietnamese $_.Language) -and (-not $init.voiceId -or $_.Id -eq $init.voiceId)
    })
    if ($voices.Count -eq 0) { Send @{ ready = $false; error = 'Không có giọng WinRT tiếng Việt khả dụng.' }; exit 1 }
    # Microsoft An được ưu tiên, nhưng chỉ sau khi đã kiểm tra locale tiếng Việt.
    $voice = @($voices | Sort-Object @{ Expression = { if ($_.DisplayName -match '\bAn\b') { 0 } else { 1 } } }, DisplayName)[0]
    $synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
    $synth.Voice = $voice
    Send @{ ready = $true; voice = $voice.DisplayName }
} catch {
    Send @{ ready = $false; error = $_.Exception.Message }
    exit 1
}

$player = $null
$memory = $null
function Stop-Playback {
    if ($null -ne $script:player) { try { $script:player.Stop() } catch { }; $script:player.Dispose(); $script:player = $null }
    if ($null -ne $script:memory) { $script:memory.Dispose(); $script:memory = $null }
}

while ($null -ne ($line = [Console]::In.ReadLine())) {
    $request = $null
    try {
        $request = $line | ConvertFrom-Json
        if ($request.action -eq 'stop') { Stop-Playback; continue }
        if ($request.action -ne 'speak' -or [string]::IsNullOrWhiteSpace($request.text) -or $request.text.Length -gt 400) {
            throw 'Yêu cầu giọng không hợp lệ.'
        }
        Stop-Playback
        $operation = $synth.SynthesizeTextToStreamAsync([string]$request.text)
        $task = $asTask.Invoke($null, @($operation))
        if (-not $task.Wait(20000)) { $operation.Cancel(); throw 'Tổng hợp giọng quá thời gian.' }
        $stream = $task.Result
        $managed = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($stream)
        $script:memory = New-Object System.IO.MemoryStream
        $managed.CopyTo($script:memory)
        $managed.Dispose(); $stream.Dispose()
        $bytes = $script:memory.ToArray()
        if ($bytes.Length -le 44) { throw 'WinRT không trả dữ liệu âm thanh.' }
        $byteRate = [BitConverter]::ToInt32($bytes, 28)
        $script:memory.Position = 0
        $script:player = New-Object System.Media.SoundPlayer
        $script:player.Stream = $script:memory
        $script:player.Play()   # Không chặn: lệnh stop kế tiếp vẫn được xử lý ngay.
        Send @{ id = $request.id; ms = [int](($bytes.Length - 44) * 1000 / [Math]::Max(1, $byteRate)) }
    } catch {
        Send @{ id = $(if ($request) { $request.id } else { $null }); error = $_.Exception.Message }
    }
}
Stop-Playback
