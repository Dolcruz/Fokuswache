param([switch]$Elevated)
$ErrorActionPreference = 'Stop'
$package = $PSScriptRoot
$installRoot = Join-Path $env:ProgramFiles 'FokusWache'
$dataRoot = Join-Path $env:ProgramData 'FokusWache'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Elevated'
    $child = Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList $arguments -Wait -PassThru
    if ($child.ExitCode -ne 0) { throw 'Installation fehlgeschlagen. Details stehen in ProgramData\FokusWache\installation.log.' }
    exit 0
}
New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
Start-Transcript -Path (Join-Path $dataRoot 'installation.log') -Append | Out-Null
try {
    $binarySource = Join-Path $package 'app'
    if (-not (Test-Path -LiteralPath (Join-Path $binarySource 'FokusWache.exe'))) { throw 'Programmdateien fehlen.' }
    $existing = Get-Service -Name FokusWache -ErrorAction SilentlyContinue
    if ($existing) { throw 'FokusWache ist bereits installiert. Für ein Update zuerst die vorhandene Installation kontrolliert beenden.' }
    New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
    Copy-Item -Path (Join-Path $binarySource '*') -Destination $installRoot -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $package 'extensions') -Destination $installRoot -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $package 'Deinstallieren.ps1') -Destination $installRoot -Force
    & icacls.exe $installRoot /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Programmordner konnte nicht geschützt werden.' }
    & icacls.exe $dataRoot /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Regelordner konnte nicht geschützt werden.' }
    $native = Join-Path $installRoot 'FokusWacheNative.exe'
    $extId = (Get-Content -LiteralPath (Join-Path $installRoot 'extensions\extension-id.txt') -Raw).Trim()
    $chromeManifest = Join-Path $installRoot 'native-chromium.json'
    $firefoxManifest = Join-Path $installRoot 'native-firefox.json'
    @{name='de.fokuswache.native';description='FokusWache';path=$native;type='stdio';allowed_origins=@("chrome-extension://$extId/")} | ConvertTo-Json | Set-Content -LiteralPath $chromeManifest -Encoding ASCII
    @{name='de.fokuswache.native';description='FokusWache';path=$native;type='stdio';allowed_extensions=@('fokuswache@local')} | ConvertTo-Json | Set-Content -LiteralPath $firefoxManifest -Encoding ASCII
    foreach ($vendor in @('Google\Chrome','BraveSoftware\Brave-Browser','Microsoft\Edge')) {
        $key = "HKLM:\SOFTWARE\$vendor\NativeMessagingHosts\de.fokuswache.native"
        New-Item -Path $key -Force | Out-Null
        Set-Item -Path $key -Value $chromeManifest
    }
    $key = 'HKLM:\SOFTWARE\Mozilla\NativeMessagingHosts\de.fokuswache.native'
    New-Item -Path $key -Force | Out-Null
    Set-Item -Path $key -Value $firefoxManifest
    New-Service -Name FokusWache -BinaryPathName ('"' + (Join-Path $installRoot 'FokusWache.exe') + '" --service') -DisplayName 'FokusWache Sperrdienst' -Description 'Zentrale Zeitkonten und Sperrregeln.' -StartupType Automatic | Out-Null
    & sc.exe failure FokusWache reset= 86400 actions= restart/2000/restart/2000/restart/5000 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Dienstwiederherstellung fehlgeschlagen.' }
    # Standard users can query the service, but cannot stop or reconfigure it.
    & sc.exe sdset FokusWache 'D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWLOCRRC;;;AU)' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Dienstberechtigungen fehlgeschlagen.' }
    $shell = New-Object -ComObject WScript.Shell
    foreach ($folder in @([Environment]::GetFolderPath('CommonDesktopDirectory'), (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'))) {
        $link = $shell.CreateShortcut((Join-Path $folder 'FokusWache.lnk'))
        $link.TargetPath = Join-Path $installRoot 'FokusWache.exe'
        $link.WorkingDirectory = $installRoot
        $link.Description = 'Webseiten, Programme und Nutzungszeiten begrenzen'
        $link.Save()
    }
    Start-Service FokusWache
    (Get-Service FokusWache).WaitForStatus('Running', [TimeSpan]::FromSeconds(20))
    Write-Output 'FokusWache installiert. Vorlagen sind deaktiviert.'
} finally { Stop-Transcript | Out-Null }
