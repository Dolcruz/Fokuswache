param([string]$Python = 'python', [string]$Iscc, [ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version = '1.0.0')
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
foreach ($binary in @('FokusWache.exe','FokusWacheNative.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $root "app\$binary"))) { throw 'Zuerst Bauen.ps1 ausführen.' }
}
if (-not $Iscc) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { $Iscc = $command.Source }
    else {
        foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles, (Join-Path $env:LOCALAPPDATA 'Programs'))) {
            $candidate = Join-Path $base 'Inno Setup 6\ISCC.exe'
            if (Test-Path -LiteralPath $candidate) { $Iscc = $candidate; break }
        }
    }
}
if (-not $Iscc -or -not (Test-Path -LiteralPath $Iscc)) { throw 'Inno Setup 6.7 oder neuer installieren oder den Compiler mit -Iscc angeben.' }
& $Python (Join-Path $root 'tools\package_licenses.py') $Version
if ($LASTEXITCODE -ne 0) { throw 'Lizenz- und Quellpaket konnte nicht erzeugt werden.' }
& $Iscc '/Q' "/DAppVersion=$Version" (Join-Path $root 'installer\FokusWache.iss')
if ($LASTEXITCODE -ne 0) { throw 'Windows-Installer konnte nicht erzeugt werden.' }
$names = @("FokusWache-Setup-$Version-x64.exe", "FokusWache-ThirdPartySources-$Version.zip")
$sums = foreach ($name in $names) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $root "dist\$name")).Hash.ToLowerInvariant()
    "$hash  $name"
}
[IO.File]::WriteAllLines((Join-Path $root 'dist\SHA256SUMS.txt'), $sums, (New-Object Text.UTF8Encoding($false)))
