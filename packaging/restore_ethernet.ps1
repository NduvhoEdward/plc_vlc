param([switch]$Apply)
$ErrorActionPreference='Stop'
$backup=Join-Path $PSScriptRoot 'ethernet-backup.json'
if(-not(Test-Path -LiteralPath $backup)){Write-Host 'No saved Ethernet changes.';exit}
if(-not $Apply){
 $helper=Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList @('-NoProfile','-File',('"' + $PSCommandPath + '"'),'-Apply') -Wait -PassThru
 exit $helper.ExitCode
}
$saved=Get-Content -LiteralPath $backup | ConvertFrom-Json
$adapter=Get-NetAdapter -Name $saved.alias
Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -IPAddress '192.168.0.10' -ErrorAction SilentlyContinue | Remove-NetIPAddress -Confirm:$false
if($saved.dhcp -eq 'Enabled'){Set-NetIPInterface -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -Dhcp Enabled}
Write-Host 'Removed the added HomePlug address and restored previous DHCP mode.'
