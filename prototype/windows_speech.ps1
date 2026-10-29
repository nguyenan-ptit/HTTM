# Windows PowerShell 5.1 worker. Text is JSON stdin, never PowerShell code.
# Output is one UTF-8 JSON document. No registry entries are created or copied.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

function Get-Diagnostic($Exception, [string]$Backend, [string]$Stage) {
    $messages = @()
    $codes = @()
    $current = $Exception
    while ($null -ne $current) {
        $messages += $current.Message
        $codes += ('0x{0:X8}' -f ($current.HResult -band 0xFFFFFFFFL))
        $current = $current.InnerException
    }
    return @{ backend = $Backend; stage = $Stage; message = ($messages -join ' -> '); hresults = $codes }
}

function Test-Vietnamese([string]$Language) {
    return $Language.ToLowerInvariant().Replace('_', '-') -in @('vi', 'vi-vn')
}

function Get-TokenLanguage($Token) {
    try {
        foreach ($hex in ($Token.GetAttribute('Language') -split ';')) {
            try {
                $name = [Globalization.CultureInfo]::GetCultureInfo([Convert]::ToInt32($hex, 16)).Name
                if (Test-Vietnamese $name) { return $name }
            } catch { }
        }
    } catch { }
    return ''
}

function Release-Com($Value) {
    if ($null -ne $Value -and [Runtime.InteropServices.Marshal]::IsComObject($Value)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Value)
    }
}

function Get-InstalledVoices {
    # Read-only inventory is independent of API activation or successful synthesis.
    $items = @()
    foreach ($root in @('HKLM:', 'HKCU:')) {
        foreach ($kind in @('Speech', 'Speech_OneCore')) {
            $path = $root + '\SOFTWARE\Microsoft\' + $kind + '\Voices\Tokens'
            if (Test-Path -LiteralPath $path) {
                foreach ($key in @(Get-ChildItem -LiteralPath $path)) {
                    try {
                        $attributes = Get-ItemProperty -LiteralPath ($key.PSPath + '\Attributes')
                        $language = ''
                        foreach ($hex in ([string]$attributes.Language -split ';')) {
                            try {
                                $candidate = [Globalization.CultureInfo]::GetCultureInfo([Convert]::ToInt32($hex, 16)).Name
                                if (Test-Vietnamese $candidate) { $language = $candidate; break }
                            } catch { }
                        }
                        if ($language) {
                            $items += @{ id = $key.Name; name = [string]$attributes.Name; language = $language; source = $kind }
                        }
                    } catch { }
                }
            }
        }
    }
    return $items
}

function Get-BackendVoices([string]$Backend) {
    if ($Backend -eq 'winrt') {
        Add-Type -AssemblyName System.Runtime.WindowsRuntime
        $null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType=WindowsRuntime]
        $voices = @([Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices)
        $items = @()
        foreach ($voice in $voices) {
            if (Test-Vietnamese $voice.Language) {
                $items += @{ id = $voice.Id; name = $voice.DisplayName; language = $voice.Language; backend = $Backend }
            }
        }
        return $items
    }
    $speaker = $null
    $category = $null
    try {
        if ($Backend -eq 'sapi') {
            $speaker = New-Object -ComObject SAPI.SpVoice
            $tokens = $speaker.GetVoices()
        } else {
            $category = New-Object -ComObject SAPI.SpObjectTokenCategory
            $category.SetId('HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices', $false)
            $tokens = $category.EnumerateTokens()
        }
        $items = @()
        foreach ($token in $tokens) {
            $language = Get-TokenLanguage $token
            if ($language) {
                $items += @{ id = $token.Id; name = $token.GetDescription(); language = $language; backend = $Backend }
            }
            Release-Com $token
        }
        Release-Com $tokens
        return $items
    } finally {
        Release-Com $speaker
        Release-Com $category
    }
}

function Invoke-Synthesis([string]$Backend, $Voice, [string]$Text, [bool]$Play, [int]$TimeoutMs) {
    $script:SpeechStage = 'voice_selection'
    if (-not (Test-Vietnamese $Voice.language)) { throw 'Refusing a voice without a Vietnamese locale.' }
    if ($Backend -eq 'winrt') {
        $synth = $null
        $stream = $null
        $managed = $null
        $memory = $null
        $player = $null
        try {
            $synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
            $selected = @([Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.Id -eq $Voice.id })
            if ($selected.Count -ne 1 -or -not (Test-Vietnamese $selected[0].Language)) { throw 'Selected Vietnamese WinRT voice is no longer available.' }
            $synth.Voice = $selected[0]
            $script:SpeechStage = 'synthesis'
            $operation = $synth.SynthesizeTextToStreamAsync($Text)
            $method = @([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
                $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetGenericArguments().Count -eq 1 -and
                $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
            })[0]
            $streamType = [Windows.Media.SpeechSynthesis.SpeechSynthesisStream, Windows.Media.SpeechSynthesis, ContentType=WindowsRuntime]
            $task = $method.MakeGenericMethod($streamType).Invoke($null, @($operation))
            if (-not $task.Wait($TimeoutMs)) { $operation.Cancel(); throw 'WinRT synthesis timed out.' }
            $stream = $task.Result
            $script:SpeechStage = 'reading_audio'
            $managed = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($stream)
            $memory = New-Object System.IO.MemoryStream
            $managed.CopyTo($memory)
            $bytes = $memory.Length
            if ($bytes -le 44) { throw 'WinRT returned no usable audio data.' }
            if ($Play) {
                $script:SpeechStage = 'playback'
                $memory.Position = 0
                $player = New-Object System.Media.SoundPlayer
                $player.Stream = $memory
                $player.PlaySync()
            }
            return @{ synthesisSucceeded = $true; audioBytes = $bytes; playbackAttempted = $Play; playbackCompleted = $(if ($Play) { $true } else { $null }) }
        } finally {
            if ($null -ne $player) { $player.Stop(); $player.Dispose() }
            if ($null -ne $memory) { $memory.Dispose() }
            if ($null -ne $managed) { $managed.Dispose() }
            if ($null -ne $stream) { $stream.Dispose() }
            if ($null -ne $synth) { $synth.Dispose() }
        }
    }
    $speaker = $null
    $token = $null
    $memory = $null
    $category = $null
    $tokens = $null
    try {
        $speaker = New-Object -ComObject SAPI.SpVoice
        # Keep the actual enumerated token. Recreating a OneCore token using
        # SAPI's default category can give SPERR_INVALID_REGISTRY_KEY.
        if ($Backend -eq 'onecore') {
            $category = New-Object -ComObject SAPI.SpObjectTokenCategory
            $category.SetId('HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices', $false)
            $tokens = $category.EnumerateTokens()
        } else { $tokens = $speaker.GetVoices() }
        foreach ($candidate in $tokens) {
            if ($candidate.Id -eq $Voice.id) { $token = $candidate; break }
            Release-Com $candidate
        }
        if ($null -eq $token) { throw 'Selected Vietnamese SAPI token is no longer available.' }
        if (-not (Get-TokenLanguage $token)) { throw 'Selected SAPI token is not Vietnamese.' }
        $speaker.Voice = $token
        # Always synthesize into a memory stream first. Probe cannot open a speaker.
        $memory = New-Object -ComObject SAPI.SpMemoryStream
        $speaker.AudioOutputStream = $memory
        $script:SpeechStage = 'synthesis'
        # SVSFlagsAsync | SVSFIsNotXML: model labels cannot be treated as SSML.
        [void]$speaker.Speak($Text, 17)
        $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMs)
        while (-not $speaker.WaitUntilDone(50)) {
            if ([DateTime]::UtcNow -gt $deadline) { [void]$speaker.Speak('', 3); throw 'SAPI synthesis timed out.' }
        }
        $data = $memory.GetData()
        $bytes = $data.Length
        if ($bytes -le 0) { throw 'SAPI returned no audio data.' }
        if ($Play) {
            $script:SpeechStage = 'playback'
            # Replay the synthesized stream through this process, never a detached app.
            $speaker.AudioOutputStream = $null
            $memory.Seek(0, 0) | Out-Null
            [void]$speaker.SpeakStream($memory, 1)
            $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMs)
            while (-not $speaker.WaitUntilDone(50)) {
                if ([DateTime]::UtcNow -gt $deadline) { [void]$speaker.Speak('', 3); throw 'SAPI playback timed out.' }
            }
        }
        return @{ synthesisSucceeded = $true; audioBytes = $bytes; playbackAttempted = $Play; playbackCompleted = $(if ($Play) { $true } else { $null }) }
    } finally {
        if ($null -ne $speaker) { try { [void]$speaker.Speak('', 3) } catch { } }
        Release-Com $memory
        Release-Com $speaker
        Release-Com $token
        Release-Com $tokens
        Release-Com $category
    }
}

try {
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($request.action -notin @('probe', 'speak') -or $request.backend -notin @('auto', 'winrt', 'sapi', 'onecore')) { throw 'Invalid worker request.' }
    if ([string]::IsNullOrWhiteSpace($request.text) -or $request.text.Length -gt 400) { throw 'Invalid speech text length.' }
    $timeoutMs = [Math]::Min(20000, [Math]::Max(1000, [int]$request.timeoutMs))
    $installed = @(Get-InstalledVoices)
    $backends = $(if ($request.backend -eq 'auto') { @('winrt', 'sapi', 'onecore') } else { @([string]$request.backend) })
    $reports = @()
    $errors = @()
    $allVoices = @()
    $success = $null
    foreach ($backend in $backends) {
        $stage = 'enumeration'
        $report = @{ backend = $backend; apiAccessible = $false; voices = @(); synthesisSucceeded = $false; audioBytes = 0; error = $null }
        try {
            $voices = @(Get-BackendVoices $backend)
            $allVoices += $voices
            $report.apiAccessible = $true
            $report.voices = $voices
            $candidates = @($voices | Where-Object { -not $request.voiceId -or $_.id -eq $request.voiceId })
            if ($candidates.Count -eq 0) { throw 'No requested Vietnamese voice is accessible through this API.' }
            # Microsoft An is preferred only after a verified Vietnamese locale.
            $voice = @($candidates | Sort-Object @{ Expression = { if ($_.name -match '\bAn\b') { 0 } else { 1 } } }, name)[0]
            $stage = 'synthesis_or_playback'
            $script:SpeechStage = $stage
            $audio = Invoke-Synthesis $backend $voice $request.text ($request.action -eq 'speak') $timeoutMs
            $report.synthesisSucceeded = $true
            $report.audioBytes = $audio.audioBytes
            $report.selectedVoice = $voice
            if ($request.action -eq 'speak') {
                $success = @{ ok = $true; action = 'speak'; backend = $backend; selectedVoice = $voice; synthesisSucceeded = $true; audioBytes = $audio.audioBytes; playbackAttempted = $true; playbackCompleted = $audio.playbackCompleted; heardConfirmed = $null; errors = $errors }
                break
            }
        } catch {
            if ($stage -eq 'synthesis_or_playback') { $stage = $script:SpeechStage }
            $errorDetail = Get-Diagnostic $_.Exception $backend $stage
            $report.error = $errorDetail
            $errors += $errorDetail
            # A failed player may already have emitted some sound. Do not
            # replay the same utterance through another backend after that.
            if ($request.action -eq 'speak' -and $stage -eq 'playback') { break }
        }
        $reports += $report
    }
    if ($request.action -eq 'probe') {
        $success = @{ ok = $true; action = 'probe'; vietnameseInstalled = ($installed.Count -gt 0 -or $allVoices.Count -gt 0); installedVoices = $installed; voices = $allVoices; backends = $reports; playbackAttempted = $false; playbackCompleted = $null; heardConfirmed = $null; errors = $errors }
    }
    if ($null -eq $success) { $success = @{ ok = $false; action = 'speak'; errors = $errors; vietnameseInstalled = ($installed.Count -gt 0 -or $allVoices.Count -gt 0); heardConfirmed = $null } }
    [Console]::Out.WriteLine(($success | ConvertTo-Json -Depth 12 -Compress))
    if (-not $success.ok) { exit 1 }
} catch {
    $failure = @{ ok = $false; error = (Get-Diagnostic $_.Exception 'worker' 'request'); heardConfirmed = $null }
    [Console]::Out.WriteLine(($failure | ConvertTo-Json -Depth 12 -Compress))
    exit 1
}
