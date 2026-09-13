[CmdletBinding()]
param(
    # Keep defaults relative to this script so the file stays ASCII-safe on Windows PowerShell 5.1.
    [string]$Repo = "",
    [string]$Mcp = "",
    [string]$ResignedIpa = "",
    [string]$Deb = "",
    [switch]$InstallIpa,
    [switch]$InstallDeb,
    [switch]$EnableRt,
    [switch]$RemoveTweakFirst,
    [int]$Seconds = 25,
    [string]$Out = ""
)

$ErrorActionPreference = "Stop"

function Resolve-ExistingFile([string]$Path, [string]$Name, [switch]$Optional) {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        if ($Optional) { return "" }
        throw "$Name path is empty"
    }
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) {
        if ($Optional) { return "" }
        throw "$Name not found: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

$scriptDir = (Resolve-Path -LiteralPath $PSScriptRoot).Path
if ([string]::IsNullOrWhiteSpace($Repo)) {
    $Repo = Join-Path $scriptDir ".."
}
$repoPath = (Resolve-Path -LiteralPath $Repo).Path
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $repoPath "..")).Path

if ([string]::IsNullOrWhiteSpace($Mcp)) {
    $Mcp = Join-Path $projectRoot "mcp.py"
}
if ([string]::IsNullOrWhiteSpace($Deb)) {
    $Deb = Join-Path $projectRoot "dist\com.seagull.cookinggomod_1.3.2_iphoneos-arm64.deb"
}
if ([string]::IsNullOrWhiteSpace($Out)) {
    $Out = Join-Path $projectRoot "_work\postfix_verify_12602.json"
}

$script = Join-Path $repoPath "tools\postfix_verify_12602.py"
if (!(Test-Path -LiteralPath $script -PathType Leaf)) { throw "postfix verifier not found: $script" }

$mcpPath = Resolve-ExistingFile $Mcp "mcp.py"
$debPath = Resolve-ExistingFile $Deb "DEB" -Optional
if ($InstallDeb -and !$debPath) { throw "-InstallDeb was set but DEB is missing: $Deb" }
if ($InstallIpa) {
    $ipaPath = Resolve-ExistingFile $ResignedIpa "resigned IPA"
} else {
    $ipaPath = ""
}

$outDir = Split-Path -Parent $Out
if ($outDir) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }

$argsList = @($script, "--mcp", $mcpPath, "--seconds", [string]$Seconds, "--out", $Out)
if ($InstallIpa) { $argsList += @("--install-ipa", $ipaPath) }
if ($InstallDeb) { $argsList += @("--install-deb", $debPath) }
if ($EnableRt) { $argsList += "--enable-rt" }
if ($RemoveTweakFirst) { $argsList += "--remove-tweak-first" }

Write-Host "== Cooking GO 1.26.02 post-fix verifier"
Write-Host "repo      : $repoPath"
Write-Host "mcp       : $mcpPath"
Write-Host "out       : $Out"
Write-Host "installIPA: $InstallIpa $ipaPath"
Write-Host "installDEB: $InstallDeb $debPath"
Write-Host "enableRt  : $EnableRt"
Write-Host ""

& python @argsList
$code = $LASTEXITCODE
Write-Host ""
Write-Host "exit code : $code"
if (Test-Path -LiteralPath $Out -PathType Leaf) {
    Write-Host "report    : $((Resolve-Path -LiteralPath $Out).Path)"
}
exit $code
