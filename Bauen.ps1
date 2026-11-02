param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$buildPython = (Get-Command $Python -ErrorAction Stop).Source
$previousPath = $env:PATH
# Resolve dependencies against this Python and Windows, without unrelated Conda DLLs.
$env:PATH = (Split-Path $buildPython -Parent) + ';' + $env:SystemRoot + '\System32;' + $env:SystemRoot
try {
$root = $PSScriptRoot
$scratch = Join-Path $root 'build'
New-Item -ItemType Directory -Force -Path $scratch | Out-Null
& $buildPython -m PyInstaller --noconfirm --clean --onedir --noconsole --name FokusWache --icon (Join-Path $root 'src\FokusWache.ico') --add-data ((Join-Path $root 'src\FokusWache.ico') + ';.') --distpath (Join-Path $scratch 'dist') --workpath (Join-Path $scratch 'main') --specpath $scratch --paths (Join-Path $root 'src') --hidden-import win32timezone --hidden-import win32ts --collect-all tzdata (Join-Path $root 'src\main.py')
if ($LASTEXITCODE -ne 0) { throw 'Build fehlgeschlagen.' }
& $buildPython -m PyInstaller --noconfirm --clean --onedir --console --name FokusWacheNative --distpath (Join-Path $scratch 'dist') --workpath (Join-Path $scratch 'native') --specpath $scratch --paths (Join-Path $root 'src') (Join-Path $root 'src\native_entry.py')
if ($LASTEXITCODE -ne 0) { throw 'Native-Build fehlgeschlagen.' }
$app = Join-Path $root 'app'
if ([IO.Path]::GetFullPath($app) -ne [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'app'))) { throw 'Ungültiger Build-Zielordner.' }
if (Test-Path -LiteralPath $app) { Remove-Item -LiteralPath $app -Recurse -Force }
New-Item -ItemType Directory -Force -Path $app | Out-Null
Copy-Item -Path (Join-Path $scratch 'dist\FokusWache\*') -Destination $app -Recurse -Force
Copy-Item -Path (Join-Path $scratch 'dist\FokusWacheNative\*') -Destination $app -Recurse -Force
} finally { $env:PATH = $previousPath }
