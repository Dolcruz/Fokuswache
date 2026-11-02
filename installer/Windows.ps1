param(
    [Parameter(Mandatory)][ValidateSet('Check','Prepare','Configure','Uninstall','Resume')][string]$Action,
    [Parameter(Mandatory)][string]$InstallRoot,
    [string]$ErrorFile
)
$ErrorActionPreference = 'Stop'
$dataRoot = Join-Path $env:ProgramData 'FokusWache'
$expectedRoot = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'FokusWache'
$vendors = @('Google\Chrome','BraveSoftware\Brave-Browser','Microsoft\Edge','Mozilla')
$sc = Join-Path $env:WINDIR 'System32\sc.exe'

function Invoke-Sc([string[]]$Arguments) {
    & $sc @Arguments | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Windows-Dienstkonfiguration fehlgeschlagen (sc.exe: $LASTEXITCODE)." }
}

function Assert-Target {
    if (-not [Environment]::Is64BitProcess -or [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\') -ine $expectedRoot) {
        throw 'FokusWache muss unter dem 64-Bit-Programmordner in FokusWache installiert werden.'
    }
    $service = Get-CimInstance Win32_Service -Filter "Name='FokusWache'"
    $expectedCommand = '"' + (Join-Path $InstallRoot 'FokusWache.exe') + '" --service'
    if ($service -and $service.PathName.Trim() -ine $expectedCommand) {
        throw 'Ein anderer Dienst verwendet bereits den Namen FokusWache. Die vorhandene Installation wurde nicht verändert.'
    }
    foreach ($vendor in $vendors) {
        $key = "HKLM:\SOFTWARE\$vendor\NativeMessagingHosts\de.fokuswache.native"
        if (Test-Path -LiteralPath $key) {
            $manifest = (Get-Item -LiteralPath $key).GetValue('')
            if ($manifest -notin @((Join-Path $InstallRoot 'native-chromium.json'), (Join-Path $InstallRoot 'native-firefox.json'))) {
                throw 'Eine andere Browserregistrierung verwendet bereits den Namen FokusWache.'
            }
        }
    }
}

function Assert-Installation {
    Assert-Target
    $stateFile = Join-Path $dataRoot 'state.json'
    if (Test-Path -LiteralPath $stateFile) {
        $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        if ($state.rules -isnot [System.Array] -or $state.usage -isnot [PSCustomObject]) { throw 'Die gespeicherten FokusWache-Regeln sind ungültig. Die Installation wurde nicht verändert.' }
        foreach ($rule in $state.rules) {
            foreach ($field in @('locked_until','timer_until')) {
                if ($rule.$field -and [DateTimeOffset]::Parse($rule.$field) -gt [DateTimeOffset]::UtcNow) {
                    throw 'Eine Regel ist noch verriegelt. Installation und Deinstallation sind erst nach Ablauf aller Verriegelungen möglich.'
                }
            }
        }
    }
    foreach ($process in Get-InstallationProcesses) {
        if ($process.Name -ieq 'FokusWache.exe' -and $process.CommandLine -notmatch '(?:^|\s)--(?:service|agent|request)(?:\s|$)') {
            throw 'Bitte schließe zuerst das FokusWache-Fenster. Angefangene Tagebucheinträge werden nicht automatisch verworfen.'
        }
    }
}

function Get-InstallationProcesses {
    Get-CimInstance Win32_Process -Filter "Name='FokusWache.exe' OR Name='FokusWacheNative.exe'" |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath -in @((Join-Path $InstallRoot 'FokusWache.exe'), (Join-Path $InstallRoot 'FokusWacheNative.exe')) }
}

function Register-Browsers {
    $native = Join-Path $InstallRoot 'FokusWacheNative.exe'
    $extensionId = (Get-Content -LiteralPath (Join-Path $InstallRoot 'extensions\extension-id.txt') -Raw).Trim()
    if ($extensionId -cnotmatch '^[a-p]{32}$') { throw 'Ungültige Chromium-Erweiterungskennung.' }
    $chromium = @{ name='de.fokuswache.native'; description='FokusWache'; path=$native; type='stdio'; allowed_origins=@("chrome-extension://$extensionId/") }
    $firefox = @{ name='de.fokuswache.native'; description='FokusWache'; path=$native; type='stdio'; allowed_extensions=@('fokuswache@local') }
    $utf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText((Join-Path $InstallRoot 'native-chromium.json'), ($chromium | ConvertTo-Json), $utf8)
    [IO.File]::WriteAllText((Join-Path $InstallRoot 'native-firefox.json'), ($firefox | ConvertTo-Json), $utf8)
    foreach ($vendor in $vendors) {
        $key = "HKLM:\SOFTWARE\$vendor\NativeMessagingHosts\de.fokuswache.native"
        New-Item -Path $key -Force | Out-Null
        Set-Item -Path $key -Value (Join-Path $InstallRoot $(if ($vendor -eq 'Mozilla') { 'native-firefox.json' } else { 'native-chromium.json' }))
    }
}

function Resume-Service {
    if (Get-Service -Name FokusWache -ErrorAction SilentlyContinue) {
        Register-Browsers
        Set-Service FokusWache -StartupType Automatic
        if ((Get-Service FokusWache).Status -ne 'Running') { Start-Service FokusWache }
        (Get-Service FokusWache).WaitForStatus('Running', [TimeSpan]::FromSeconds(20))
    }
}

function Prepare-Installation {
    Assert-Installation
    try {
        $service = Get-Service -Name FokusWache -ErrorAction SilentlyContinue
        if ($service) {
            Set-Service FokusWache -StartupType Disabled
            if ($service.Status -ne 'Stopped') {
                & $sc stop FokusWache | Out-Null
                $stopCode = $LASTEXITCODE
                try { (Get-Service FokusWache).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(15)) }
                catch { throw "Windows hat den Dienststopp nicht bestätigt (sc.exe: $stopCode). $($_.Exception.Message)" }
            }
            # Check again after stopping so a newly saved lock is not bypassed.
            Assert-Installation
        }
        foreach ($vendor in $vendors) {
            $key = "HKLM:\SOFTWARE\$vendor\NativeMessagingHosts\de.fokuswache.native"
            if (Test-Path -LiteralPath $key) { Remove-Item -LiteralPath $key }
        }
        foreach ($process in Get-InstallationProcesses) {
            if ($process.Name -ieq 'FokusWacheNative.exe' -or $process.CommandLine -match '(?:^|\s)--agent(?:\s|$)') {
                Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
        $failure = $_
        Resume-Service
        throw $failure
    }
}

try {
    if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Die Windows-Einrichtung benötigt Administratorrechte.'
    }
    if ($ErrorFile) { [IO.File]::WriteAllText($ErrorFile, '') }
    Assert-Target
    switch ($Action) {
        'Check' { Assert-Installation }
        'Prepare' { Prepare-Installation }
        'Configure' {
            if ([IO.Path]::GetFullPath($InstallRoot).TrimEnd('\') -ine $expectedRoot) { throw 'Ungültiger Installationsordner.' }
            foreach ($file in @('FokusWache.exe','FokusWacheNative.exe','extensions\extension-id.txt')) {
                if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot $file))) { throw "Programmdatei fehlt: $file" }
            }
            New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
            & icacls.exe $InstallRoot /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'Programmordner konnte nicht geschützt werden.' }
            & icacls.exe $dataRoot /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'Regelordner konnte nicht geschützt werden.' }
            $command = '"' + (Join-Path $InstallRoot 'FokusWache.exe') + '" --service'
            if (-not (Get-Service FokusWache -ErrorAction SilentlyContinue)) {
                New-Service -Name FokusWache -BinaryPathName $command -DisplayName 'FokusWache Sperrdienst' -Description 'Zentrale Zeitkonten und Sperrregeln.' -StartupType Automatic | Out-Null
            }
            Invoke-Sc @('failure','FokusWache','reset=','86400','actions=','restart/2000/restart/2000/restart/5000')
            Invoke-Sc @('sdset','FokusWache','D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWLOCRRC;;;AU)')
            Resume-Service
        }
        'Uninstall' {
            Prepare-Installation
            try {
                Get-NetFirewallRule -ErrorAction Stop |
                    Where-Object { $_.DisplayName -match '^FokusWache - (Gesamtnetz (ausgehend|eingehend)|Browser [a-f0-9]{16})$' } |
                    Remove-NetFirewallRule
                # Only remove legacy shortcuts that point to this installation.
                $shell = New-Object -ComObject WScript.Shell
                foreach ($folder in @([Environment]::GetFolderPath('CommonDesktopDirectory'), (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'))) {
                    $shortcut = Join-Path $folder 'FokusWache.lnk'
                    if ((Test-Path -LiteralPath $shortcut) -and $shell.CreateShortcut($shortcut).TargetPath -ieq (Join-Path $InstallRoot 'FokusWache.exe')) { Remove-Item -LiteralPath $shortcut }
                }
                if (Get-Service FokusWache -ErrorAction SilentlyContinue) { Invoke-Sc @('delete','FokusWache') }
            } catch {
                $failure = $_
                Resume-Service
                throw $failure
            }
        }
        'Resume' { Resume-Service }
    }
    exit 0
} catch {
    if ($ErrorFile) { [IO.File]::WriteAllText($ErrorFile, $_.Exception.Message, (New-Object Text.UTF8Encoding($false))) }
    Write-Error $_
    exit 1
}
