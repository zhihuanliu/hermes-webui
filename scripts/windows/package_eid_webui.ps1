[CmdletBinding()]
param(
    [string]$Image = "hermes-webui-eid:latest",
    [string]$OutputDir = "release\hermes-webui-eid",
    [string]$TarName = "hermes-webui-eid.tar",
    [switch]$NoCache,
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    $scriptDir = Split-Path -Parent $PSCommandPath
    return (Resolve-Path (Join-Path $scriptDir "..\..")).Path
}

function Invoke-Checked {
    param(
        [string]$Title,
        [string[]]$Command
    )
    Write-Host ""
    Write-Host "== $Title"
    Write-Host ("   " + ($Command -join " "))
    $exe = $Command[0]
    $args = @($Command | Select-Object -Skip 1)
    & $exe @args
    if ($LASTEXITCODE -ne 0) {
        throw "$Title failed with exit code $LASTEXITCODE"
    }
}

function Set-EnvLine {
    param(
        [string]$Content,
        [string]$Key,
        [string]$Value
    )
    $escapedKey = [regex]::Escape($Key)
    $line = "$Key=$Value"
    $regex = [System.Text.RegularExpressions.Regex]::new("(?m)^$escapedKey=.*$")
    if ($regex.IsMatch($Content)) {
        return $regex.Replace($Content, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $line })
    }
    return ($Content.TrimEnd() + [Environment]::NewLine + $line + [Environment]::NewLine)
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

$packageDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)
New-Item -ItemType Directory -Force -Path $packageDir | Out-Null
$outputPath = Join-Path $packageDir $TarName

$buildCommand = @("docker", "build", "-t", $Image, ".")
if ($NoCache) {
    $buildCommand = @("docker", "build", "--no-cache", "-t", $Image, ".")
}

Invoke-Checked -Title "Build Hermes WebUI image" -Command $buildCommand

if (-not $SkipVerify) {
    Invoke-Checked `
        -Title "Verify chatbot.html in image" `
        -Command @("docker", "run", "--rm", $Image, "head", "-50", "/apptoo/static/chatbot.html")
}

Invoke-Checked `
    -Title "Save Hermes WebUI image" `
    -Command @("docker", "save", $Image, "-o", $outputPath)

Copy-Item -Force (Join-Path $repoRoot "docker-compose.eid-webui.yml") (Join-Path $packageDir "docker-compose.yml")
Copy-Item -Force (Join-Path $repoRoot "scripts\linux\deploy_eid_webui.sh") (Join-Path $packageDir "deploy.sh")
Copy-Item -Force (Join-Path $repoRoot ".env.eid-webui.deploy.example") (Join-Path $packageDir "deploy.env.example")

$envContent = Get-Content -Path (Join-Path $repoRoot ".env.eid-webui.deploy.example") -Raw
$envContent = Set-EnvLine $envContent "HERMES_WEBUI_IMAGE" $Image
Set-Content -Path (Join-Path $packageDir "deploy.env") -Value $envContent -Encoding ascii

Write-Host ""
Write-Host "Done."
Write-Host "Image: $Image"
Write-Host "Tar:   $outputPath"
Write-Host "Package directory: $packageDir"
Write-Host ""
Write-Host "Upload this directory to Linux, then run:"
Write-Host "  bash deploy.sh"
