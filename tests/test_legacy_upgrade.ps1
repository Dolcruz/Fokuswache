param([Parameter(Mandatory)][string]$SetupPath)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') { throw 'Disposable Windows runner required.' }
if (Get-Service FokusWache -ErrorAction SilentlyContinue) { throw 'Previous installer test must uninstall its service first.' }
$root = Split-Path $PSScriptRoot -Parent
$SetupPath = (Resolve-Path -LiteralPath $SetupPath).Path
$legacy = Join-Path $root 'build\legacy'
$revision = '171e40cc6df6a95941072f0bcdef9f49e04c466e'
New-Item -ItemType Directory -Force -Path $legacy | Out-Null
& git fetch origin $revision --depth=1
if ($LASTEXITCODE -ne 0) { throw 'Historical source commit could not be fetched.' }
$archive = Join-Path $root 'build\legacy.tar'
& git archive --format=tar "--output=$archive" $revision
if ($LASTEXITCODE -ne 0) { throw 'Historical source archive could not be created.' }
& tar.exe -xf $archive -C $legacy
if ($LASTEXITCODE -ne 0) { throw 'Historical source archive could not be extracted.' }
& (Join-Path $legacy 'Bauen.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Historical application build failed.' }
& (Join-Path $legacy 'Installieren.ps1')
$installRoot = Join-Path $env:ProgramFiles 'FokusWache'
$stateFile = Join-Path $env:ProgramData 'FokusWache\state.json'
$before = @((Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json).rules.id)
if ((Get-Service FokusWache).Status -ne 'Running') { throw 'Historical service did not start.' }
$log = Join-Path $root 'build\installer-test\legacy-upgrade.log'
$setup = Start-Process -FilePath $SetupPath -ArgumentList ('/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="' + $log + '"') -WindowStyle Hidden -Wait -PassThru
if ($setup.ExitCode -ne 0) { throw "Historical upgrade failed (exit $($setup.ExitCode))." }
if ((Get-Service FokusWache).Status -ne 'Running') { throw 'Upgraded service did not start.' }
$after = @((Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json).rules.id)
if (@(Compare-Object $before $after).Count -ne 0) { throw 'Historical upgrade lost saved rules.' }
if (Test-Path -LiteralPath (Join-Path $installRoot 'Deinstallieren.ps1')) { throw 'Retired manual uninstaller remains.' }
Write-Output 'PASS: Published historical application upgrades with all saved rule IDs preserved.'
$uninstaller = (Get-ChildItem -LiteralPath $installRoot -Filter 'unins*.exe').FullName
$process = Start-Process -FilePath $uninstaller -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0 -or (Get-Service FokusWache -ErrorAction SilentlyContinue)) { throw 'Upgraded application did not uninstall cleanly.' }
Write-Output 'PASS: Upgraded service uninstalls normally.'
