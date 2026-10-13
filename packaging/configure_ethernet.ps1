param([switch]$Apply)
$ErrorActionPreference='Stop'
$backup=Join-Path $PSScriptRoot 'ethernet-backup.json'
$adapters=@(Get-NetAdapter -Physical | Where-Object { $_.NdisPhysicalMedium -eq 14 })
if($adapters.Count -ne 1){Write-Host 'More than one wired adapter or none detected. Select your HomePlug Ethernet adapter manually in Windows.';exit 2}
$adapter=$adapters[0]
$ips=@(Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue)
if($ips | Where-Object {$_.IPAddress -like '192.168.0.*' -and $_.PrefixLength -eq 24}){Write-Host 'Ethernet subnet is already configured.';exit 0}
if(-not $Apply){
 Write-Host 'HomePlug needs Ethernet 192.168.0.10 / 24. Windows will ask permission to configure the wired adapter. Wi-Fi internet is preserved.'
 $helper=Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList @('-NoProfile','-File',('"' + $PSCommandPath + '"'),'-Apply') -Wait -PassThru
 exit $helper.ExitCode
}
if(-not(Test-Path -LiteralPath $backup)){
 $interface=Get-NetIPInterface -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4
 @{alias=$adapter.Name;interfaceIndex=$adapter.ifIndex;dhcp=[string]$interface.Dhcp;addresses=@($ips | Select-Object IPAddress,PrefixLength);gateways=@(Get-NetRoute -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Select-Object NextHop,RouteMetric)} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $backup
}
Set-NetIPInterface -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -Dhcp Disabled
# Retain existing static addresses. Add only the dedicated HomePlug subnet.
New-NetIPAddress -InterfaceIndex $adapter.ifIndex -IPAddress '192.168.0.10' -PrefixLength 24 -AddressFamily IPv4 | Out-Null
Write-Host 'Dedicated HomePlug address configured. No Ethernet default gateway was added.'
