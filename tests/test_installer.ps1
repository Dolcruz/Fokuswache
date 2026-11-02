param([Parameter(Mandatory)][string]$SetupPath, [Parameter(Mandatory)][string]$InvalidSetupPath)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') {
    throw 'Dieser Integrationstest darf nur auf einem frischen GitHub-Windows-Runner laufen.'
}
$installRoot = Join-Path $env:ProgramFiles 'FokusWache'
$dataRoot = Join-Path $env:ProgramData 'FokusWache'
if ((Get-Service FokusWache -ErrorAction SilentlyContinue) -or (Test-Path -LiteralPath $installRoot) -or (Test-Path -LiteralPath $dataRoot)) {
    throw 'Der Integrationstest benötigt einen Rechner ohne vorhandene FokusWache-Installation oder Regeln.'
}
$SetupPath = (Resolve-Path -LiteralPath $SetupPath).Path
$scratch = Join-Path (Split-Path $PSScriptRoot -Parent) 'build\installer-test'
New-Item -ItemType Directory -Force -Path $scratch | Out-Null
$uninstallKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{3E33A31B-5C5C-4B35-A278-F9E0C423230C}_is1'
$counter = 0

function Assert-True($Value, [string]$Message) {
    if (-not $Value) { throw $Message }
    Write-Host ('PASS: ' + $Message)
}

function Invoke-Package([string]$Path, [string]$Name, [bool]$Success, [string]$Extra = '') {
    $log = Join-Path $scratch ($Name + '.log')
    $process = Start-Process -FilePath $Path -ArgumentList ('/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="' + $log + '" ' + $Extra) -WindowStyle Hidden -Wait -PassThru
    Assert-True (($process.ExitCode -eq 0) -eq $Success) "$Name returned the expected success/failure result (exit $($process.ExitCode))"
}

function Request-Service($Payload) {
    $script:counter++
    $requestPath = Join-Path $scratch "request-$counter.json"
    $responsePath = Join-Path $scratch "response-$counter.json"
    $Payload | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $requestPath -Encoding UTF8
    $binary = Join-Path $installRoot 'FokusWache.exe'
    $process = Start-Process -FilePath $binary -ArgumentList ('--request "' + $requestPath + '" --response "' + $responsePath + '"') -WindowStyle Hidden -Wait -PassThru
    Assert-True ($process.ExitCode -eq 0) 'Compiled client completed'
    $response = Get-Content -LiteralPath $responsePath -Raw | ConvertFrom-Json
    if ($response.error) { throw $response.error }
    return $response
}

$mutex = New-Object Threading.Mutex($false, 'Global\FokusWache.Installer')
try { Invoke-Package $SetupPath 'parallel-install' $false } finally { $mutex.Dispose() }
Assert-True (-not (Test-Path -LiteralPath $installRoot)) 'Rejected parallel install creates no program directory'
Invoke-Package $SetupPath 'install' $true
Assert-True ((Get-Service FokusWache).Status -eq 'Running') 'Windows service is running after installation'
Assert-True (Test-Path -LiteralPath $uninstallKey) 'Installed Apps entry exists'
Assert-True (Test-Path -LiteralPath (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\FokusWache.lnk')) 'Start menu shortcut exists'
Assert-True (Test-Path -LiteralPath (Join-Path $installRoot 'licenses\Python-LICENSE.txt')) 'Runtime license notices are installed'
$status = Request-Service @{op='status'}
Assert-True (@($status.rules).Count -eq 2) 'Compiled client can read the initial rules'
Assert-True (@($status.rules | Where-Object enabled).Count -eq 0) 'Default rules are disabled'
foreach ($vendor in @('Google\Chrome','BraveSoftware\Brave-Browser','Microsoft\Edge','Mozilla')) {
    Assert-True (Test-Path -LiteralPath "HKLM:\SOFTWARE\$vendor\NativeMessagingHosts\de.fokuswache.native") "Native messaging registered for $vendor"
}

# A real application window must open from the installed build. Updates must not close it.
$uiProcess = Start-Process -FilePath (Join-Path $installRoot 'FokusWache.exe') -WindowStyle Hidden -PassThru
Assert-True ($uiProcess.WaitForInputIdle(20000)) 'Installed Qt interface reaches its message loop'
$uiProcess.Refresh()
Assert-True (-not $uiProcess.HasExited) 'Installed Qt interface remains running'
Invoke-Package $SetupPath 'running-window' $false
$uiProcess.Refresh()
Assert-True (-not $uiProcess.HasExited) 'Rejected update preserves the open application'
& python (Join-Path $PSScriptRoot 'close_installed_window.py') $uiProcess.Id
if ($LASTEXITCODE -ne 0) { throw 'The installed application window could not be closed normally.' }
Assert-True ($uiProcess.WaitForExit(20000)) 'Installed Qt interface exits after its normal close request'
$journal = Join-Path $env:LOCALAPPDATA 'FokusWache\zeitprotokoll.sqlite3'
Assert-True (Test-Path -LiteralPath $journal) 'Installed interface creates its local journal'
$journalHash = (Get-FileHash -LiteralPath $journal).Hash

$rule = @{id='installer-regression';name='Installation test';kind='apps';targets=@('C:\Games\FokusWache-Test\example.exe');enabled=$true;daily_minutes=60}
[void](Request-Service @{op='save';rule=$rule})
'Retired application component' | Set-Content -LiteralPath (Join-Path $installRoot 'Deinstallieren.ps1')
Invoke-Package $SetupPath 'update' $true
Assert-True (-not (Test-Path -LiteralPath (Join-Path $installRoot 'Deinstallieren.ps1'))) 'Update retires the previous manual uninstaller'
$status = Request-Service @{op='status'}
Assert-True (@($status.rules | Where-Object id -EQ 'installer-regression').Count -eq 1) 'Update preserves the saved rule'
Assert-True ((Get-FileHash -LiteralPath $journal).Hash -eq $journalHash) 'Update preserves the journal bytes'

Invoke-Package (Resolve-Path -LiteralPath $InvalidSetupPath).Path 'configuration-failure' $false
Invoke-Package $SetupPath 'repair-configuration' $true
$status = Request-Service @{op='status'}
Assert-True (@($status.rules | Where-Object id -EQ 'installer-regression').Count -eq 1) 'Repair preserves existing rules after a configuration failure'
$failure = Start-Process -FilePath powershell.exe -ArgumentList ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'uninstall_failure.ps1') + '" -InstallRoot "' + $installRoot + '"') -WindowStyle Hidden -Wait -PassThru
Assert-True ($failure.ExitCode -ne 0) 'Injected cleanup failure is reported'
Assert-True ((Get-Service FokusWache).Status -eq 'Running') 'Failed cleanup restores the running service'
Assert-True (Test-Path -LiteralPath (Join-Path $installRoot 'FokusWache.exe')) 'Failed cleanup preserves the application files'

$uninstaller = (Get-ChildItem -LiteralPath $installRoot -Filter 'unins*.exe').FullName
$mutex = New-Object Threading.Mutex($false, 'Global\FokusWache.Installer')
try { Invoke-Package $uninstaller 'parallel-uninstall' $false } finally { $mutex.Dispose() }
[void](Request-Service @{op='lock';id='installer-regression';until=[DateTimeOffset]::UtcNow.AddHours(1).ToString('o')})
Invoke-Package $SetupPath 'locked-update' $false
Invoke-Package $uninstaller 'locked-uninstall' $false
Assert-True ((Get-Service FokusWache).Status -eq 'Running') 'Rejected locked operations leave the service running'
Assert-True (Test-Path -LiteralPath $uninstaller) 'Rejected locked uninstall leaves program files intact'

# Administrative fixture cleanup happens only on the disposable runner.
Stop-Service FokusWache
(Get-Service FokusWache).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(15))
$stateFile = Join-Path $dataRoot 'state.json'
$state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
($state.rules | Where-Object id -EQ 'installer-regression').locked_until = $null
[IO.File]::WriteAllText($stateFile, ($state | ConvertTo-Json -Depth 20), (New-Object Text.UTF8Encoding($false)))
Start-Service FokusWache
(Get-Service FokusWache).WaitForStatus('Running', [TimeSpan]::FromSeconds(20))

Stop-Service FokusWache
(Get-Service FokusWache).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(15))
$savedState = [IO.File]::ReadAllBytes($stateFile)
$binaryHash = (Get-FileHash -LiteralPath (Join-Path $installRoot 'FokusWache.exe')).Hash
[IO.File]::WriteAllText($stateFile, 'broken')
Invoke-Package $SetupPath 'corrupt-state' $false
Assert-True ((Get-Content -LiteralPath $stateFile -Raw) -eq 'broken') 'Rejected installation preserves unreadable state for recovery'
Assert-True ((Get-FileHash -LiteralPath (Join-Path $installRoot 'FokusWache.exe')).Hash -eq $binaryHash) 'Rejected installation preserves the installed binary'
[IO.File]::WriteAllBytes($stateFile, $savedState)
Start-Service FokusWache
(Get-Service FokusWache).WaitForStatus('Running', [TimeSpan]::FromSeconds(20))

Invoke-Package $SetupPath 'wrong-directory' $false '/DIR=C:\FokusWache-Wrong-Target'
Assert-True (-not (Test-Path -LiteralPath 'C:\FokusWache-Wrong-Target')) 'Unsupported install directory receives no files'
$keepFile = Join-Path $installRoot 'personal-note.txt'
'Do not delete untracked user files.' | Set-Content -LiteralPath $keepFile
Invoke-Package $uninstaller 'uninstall' $true
Assert-True (-not (Get-Service FokusWache -ErrorAction SilentlyContinue)) 'Uninstall removes the Windows service'
Assert-True (-not (Test-Path -LiteralPath $uninstallKey)) 'Uninstall removes the Installed Apps entry'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $installRoot 'FokusWache.exe'))) 'Uninstall removes installed program files'
Assert-True (Test-Path -LiteralPath $stateFile) 'Uninstall retains rules and time accounts'
Assert-True ((Get-FileHash -LiteralPath $journal).Hash -eq $journalHash) 'Uninstall retains the journal bytes'
Assert-True (Test-Path -LiteralPath $keepFile) 'Uninstall retains untracked user files'
foreach ($vendor in @('Google\Chrome','BraveSoftware\Brave-Browser','Microsoft\Edge','Mozilla')) {
    Assert-True (-not (Test-Path -LiteralPath "HKLM:\SOFTWARE\$vendor\NativeMessagingHosts\de.fokuswache.native")) "Uninstall removes native messaging for $vendor"
}
Write-Output 'Installer integration checks passed.'
