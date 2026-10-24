param(
    [Parameter(Mandatory=$true)][string]$ServiceExecutable,
    [Parameter(Mandatory=$true)][string]$ExpectedSHA256,
    [Parameter(Mandatory=$true)][string]$PublisherThumbprint,
    [Parameter(Mandatory=$true)][System.Management.Automation.PSCredential]$ServiceCredential
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
if (Get-Service -Name AuditOSTallyReader -ErrorAction SilentlyContinue) {
    throw 'An existing service must be stopped and upgraded using a reviewed release; it will not be overwritten.'
}
New-Service -Name AuditOSTallyReader -DisplayName 'AuditOS Tally accounting reader' `
    -BinaryPathName ('"' + $resolvedExecutable + '"') -StartupType Automatic -Credential $ServiceCredential
