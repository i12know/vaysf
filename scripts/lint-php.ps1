[CmdletBinding()]
param(
    [switch]$All,
    [string]$BaseRef = "main",
    [string]$PhpBin = $env:PHP_BIN,
    [string[]]$Path = @("plugins/vaysf")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-PhpExecutable {
    param([string]$RequestedPhpBin)

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($RequestedPhpBin)) {
        $candidates += $RequestedPhpBin
    }
    if ($env:OS -eq "Windows_NT") {
        $candidates += "S:\php\php.exe"
    }
    $phpCommand = Get-Command php -ErrorAction SilentlyContinue
    if ($phpCommand) {
        $candidates += $phpCommand.Source
    }
    $candidates += "php"

    foreach ($candidate in $candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) {
            continue
        }
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }

    throw "PHP executable not found. Set PHP_BIN, install php on PATH, or use S:\php\php.exe on this Windows workspace."
}

function Get-PhpFiles {
    param(
        [bool]$UseAll,
        [string]$DiffBaseRef,
        [string[]]$TargetPaths
    )

    $paths = $TargetPaths | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    if (-not $paths) {
        $paths = @("plugins/vaysf")
    }

    if ($UseAll) {
        $gitArgs = @("ls-files", "--") + $paths
        $files = & git @gitArgs
        if ($LASTEXITCODE -ne 0) {
            throw "git ls-files failed."
        }
    } else {
        $gitArgs = @("diff", "--name-only", "--diff-filter=ACMRT", "$DiffBaseRef...HEAD", "--") + $paths
        $files = & git @gitArgs 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not diff against '$DiffBaseRef'; falling back to all tracked PHP files."
            $gitArgs = @("ls-files", "--") + $paths
            $files = & git @gitArgs
            if ($LASTEXITCODE -ne 0) {
                throw "git ls-files failed."
            }
        }
    }

    return $files |
        Where-Object { $_ -match '\.php$' -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
        Sort-Object -Unique
}

$php = Resolve-PhpExecutable -RequestedPhpBin $PhpBin
$phpFiles = @(Get-PhpFiles -UseAll:$All.IsPresent -DiffBaseRef $BaseRef -TargetPaths $Path)

if (-not $phpFiles) {
    Write-Host "No PHP files to lint."
    exit 0
}

Write-Host "Using PHP: $php"
$failed = $false
foreach ($file in $phpFiles) {
    $output = & $php -l $file 2>&1
    if ($LASTEXITCODE -ne 0) {
        $failed = $true
        Write-Host "FAIL $file"
        $output | ForEach-Object { Write-Host $_ }
    } else {
        Write-Host "OK $file"
    }
}

if ($failed) {
    exit 1
}
