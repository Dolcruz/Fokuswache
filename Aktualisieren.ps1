$ErrorActionPreference = 'Stop'
$installRoot = Join-Path $env:ProgramFiles 'FokusWache'
$dataRoot = Join-Path $env:ProgramData 'FokusWache'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $p = Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"') -PassThru -Wait
    exit $p.ExitCode
}
Start-Transcript -Path (Join-Path $dataRoot 'update.log') -Append | Out-Null
$result = Join-Path $dataRoot 'update-result.txt'
$restart = $false
$nativeKeys = @{}
try {
    $state = Get-Content -LiteralPath (Join-Path $dataRoot 'state.json') -Raw | ConvertFrom-Json
    foreach ($r in $state.rules) {
        if ($r.locked_until -and [DateTimeOffset]::Parse($r.locked_until) -gt [DateTimeOffset]::UtcNow) { throw 'Update erst nach Ablauf der Verriegelungen.' }
    }
    Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class FokusProcessPath {
 [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
 [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern bool QueryFullProcessImageName(IntPtr p, int flags, StringBuilder name, ref int length);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr p);
 public static string Get(int pid) { var p=OpenProcess(0x1000,false,pid); if(p==IntPtr.Zero)return ""; try { var b=new StringBuilder(32768); int n=b.Capacity; return QueryFullProcessImageName(p,0,b,ref n)?b.ToString():""; } finally {CloseHandle(p);} }
}
'@
    Set-Service FokusWache -StartupType Disabled
    $restart = $true
    foreach ($vendor in @('Google\Chrome','BraveSoftware\Brave-Browser','Microsoft\Edge','Mozilla')) {
        $key = "HKLM:\SOFTWARE\$vendor\NativeMessagingHosts\de.fokuswache.native"
        if (Test-Path -LiteralPath $key) {
            $nativeKeys[$key] = (Get-Item -LiteralPath $key).GetValue('')
            Remove-Item -LiteralPath $key
        }
    }
    Stop-Service FokusWache -ErrorAction SilentlyContinue
    (Get-Service FokusWache).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(15))
    Get-Process FokusWache,FokusWacheNative -ErrorAction SilentlyContinue | Where-Object { [FokusProcessPath]::Get($_.Id) -in @((Join-Path $installRoot 'FokusWache.exe'), (Join-Path $installRoot 'FokusWacheNative.exe')) } | Stop-Process -Force
    Copy-Item -Path (Join-Path $PSScriptRoot 'app\*') -Destination $installRoot -Recurse -Force
    Copy-Item -Path (Join-Path $PSScriptRoot 'extensions\*') -Destination (Join-Path $installRoot 'extensions') -Recurse -Force
    'OK' | Set-Content -LiteralPath $result
} catch {
    ($_ | Out-String) | Set-Content -LiteralPath $result
    throw
} finally {
    foreach ($key in $nativeKeys.Keys) {
        New-Item -Path $key -Force | Out-Null
        Set-Item -Path $key -Value $nativeKeys[$key]
    }
    if ($restart) {
        Set-Service FokusWache -StartupType Automatic
        Start-Service FokusWache
        (Get-Service FokusWache).WaitForStatus('Running', [TimeSpan]::FromSeconds(20))
    }
    Stop-Transcript | Out-Null
}
