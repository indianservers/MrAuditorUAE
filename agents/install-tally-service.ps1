param(
    [Parameter(Mandatory=$true)][string]$ServiceExecutable,
    [Parameter(Mandatory=$true)][string]$ExpectedSHA256,
    [Parameter(Mandatory=$true)][string]$PublisherThumbprint,
    [System.Management.Automation.PSCredential]$ServiceCredential,
    [switch]$Update
)
$ErrorActionPreference = 'Stop'
$resolvedExecutable = (Resolve-Path -LiteralPath $ServiceExecutable).Path
$signature = Get-AuthenticodeSignature -LiteralPath $resolvedExecutable
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Thumbprint -ne $PublisherThumbprint) {
    throw 'A valid release signature from the pinned publisher is required.'
}
if ((Get-FileHash -LiteralPath $resolvedExecutable -Algorithm SHA256).Hash -ne $ExpectedSHA256) {
    throw 'The service executable differs from the approved release hash.'
}
$existingService = Get-CimInstance -ClassName Win32_Service -Filter "Name='AuditOSTallyReader'"
if ($existingService) {
    if (-not $Update) { throw 'Use -Update with a verified new release to change an existing service.' }
    $previousPath = $existingService.PathName
    $wasRunning = $existingService.State -eq 'Running'
    Stop-Service -Name AuditOSTallyReader
    try {
        $changed = Invoke-CimMethod -InputObject $existingService -MethodName Change -Arguments @{PathName=('"' + $resolvedExecutable + '"')}
        if ($changed.ReturnValue -ne 0) { throw 'The service binary path could not be updated.' }
        if ($wasRunning) { Start-Service -Name AuditOSTallyReader }
    } catch {
        $null = Invoke-CimMethod -InputObject $existingService -MethodName Change -Arguments @{PathName=$previousPath}
        if ($wasRunning) { Start-Service -Name AuditOSTallyReader }
        throw
    }
    return
}
if ($Update) { throw 'There is no existing service to update.' }
if (-not $ServiceCredential) { throw 'A vault-enrolled Windows service account is required for installation.' }
New-Service -Name AuditOSTallyReader -DisplayName 'AuditOS Tally accounting reader' `
    -BinaryPathName ('"' + $resolvedExecutable + '"') -StartupType Automatic -Credential $ServiceCredential
