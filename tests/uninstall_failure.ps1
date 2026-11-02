param([Parameter(Mandatory)][string]$InstallRoot)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') { throw 'Disposable Windows runner required.' }
function Get-NetFirewallRule {
    [CmdletBinding()]param()
    throw 'Synthetic firewall cleanup failure.'
}
& (Join-Path $InstallRoot 'installer\Windows.ps1') -Action Uninstall -InstallRoot $InstallRoot
