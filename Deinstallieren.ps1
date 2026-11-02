$ErrorActionPreference = 'Stop'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"') -Wait
    exit
}
$dataRoot = Join-Path $env:ProgramData 'FokusWache'
$stateFile = Join-Path $dataRoot 'state.json'
if (Test-Path -LiteralPath $stateFile) {
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    foreach ($rule in $state.rules) {
        if ($rule.locked_until -and [DateTimeOffset]::Parse($rule.locked_until) -gt [DateTimeOffset]::UtcNow) {
            throw 'Deinstallation ist erst nach Ablauf aller Verriegelungen verfügbar.'
        }
    }
}
Stop-Service FokusWache -ErrorAction SilentlyContinue
$installRoot = Join-Path $env:ProgramFiles 'FokusWache'
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class FokusRemovalPath {
 [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
 [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern bool QueryFullProcessImageName(IntPtr p, int flags, StringBuilder name, ref int length);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr p);
 public static string Get(int pid) { var p=OpenProcess(0x1000,false,pid); if(p==IntPtr.Zero)return ""; try { var b=new StringBuilder(32768); int n=b.Capacity; return QueryFullProcessImageName(p,0,b,ref n)?b.ToString():""; } finally {CloseHandle(p);} }
}
'@
Get-Process FokusWache,FokusWacheNative -ErrorAction SilentlyContinue | Where-Object { [FokusRemovalPath]::Get($_.Id) -in @((Join-Path $installRoot 'FokusWache.exe'), (Join-Path $installRoot 'FokusWacheNative.exe')) } | Stop-Process -Force
& sc.exe delete FokusWache | Out-Null
Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object DisplayName -Like 'FokusWache -*' | Remove-NetFirewallRule
foreach ($vendor in @('Google\Chrome','BraveSoftware\Brave-Browser','Microsoft\Edge','Mozilla')) {
    $key = "HKLM:\SOFTWARE\$vendor\NativeMessagingHosts\de.fokuswache.native"
    if (Test-Path $key) { Remove-Item -LiteralPath $key }
}
foreach ($folder in @([Environment]::GetFolderPath('CommonDesktopDirectory'), (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'))) {
    $shortcut = Join-Path $folder 'FokusWache.lnk'
    if (Test-Path -LiteralPath $shortcut) { Remove-Item -LiteralPath $shortcut }
}
Write-Output 'Dienst, Netzregeln und Verknüpfungen entfernt. Programmdateien und gespeicherte Zeitkonten bleiben zur kontrollierten Entfernung erhalten.'
