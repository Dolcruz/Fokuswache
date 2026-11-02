$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') { throw 'Disposable Windows runner required.' }
$root = Split-Path $PSScriptRoot -Parent
$idFile = Join-Path $root 'extensions\extension-id.txt'
$saved = [IO.File]::ReadAllBytes($idFile)
try {
    [IO.File]::WriteAllText($idFile, 'invalid')
    & "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /Q "/O$root\build\invalid-setup" /FInvalidSetup (Join-Path $root 'installer\FokusWache.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Invalid input fixture could not be compiled.' }
} finally { [IO.File]::WriteAllBytes($idFile, $saved) }
