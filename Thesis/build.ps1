#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Git for Windows supplies the Perl interpreter needed by latexmk. On Ubuntu,
# Perl is installed as a normal system command and no PATH adjustment is needed.
if ($IsWindows -or $env:OS -eq 'Windows_NT') {
    $gitPerlBin = 'C:\Program Files\Git\usr\bin'
    if (Test-Path -LiteralPath (Join-Path $gitPerlBin 'perl.exe')) {
        $env:Path = "$gitPerlBin$([IO.Path]::PathSeparator)$env:Path"
    }
}

$latexmkCommand = Get-Command latexmk -ErrorAction SilentlyContinue
$latexmk = if ($latexmkCommand) { $latexmkCommand.Source } else { $null }
if (-not $latexmk -and ($IsWindows -or $env:OS -eq 'Windows_NT')) {
    $miktexLatexmk = 'C:\Users\Probe\AppData\Local\Programs\MiKTeX\miktex\bin\x64\latexmk.exe'
    if (Test-Path -LiteralPath $miktexLatexmk) {
        $latexmk = $miktexLatexmk
    }
}

if (-not $latexmk) {
    if ($IsLinux) {
        Write-Error "latexmk was not found. Install the Ubuntu dependencies with: sudo apt install latexmk texlive-latex-extra texlive-science"
    } else {
        Write-Error "latexmk was not found. Install MiKTeX (including latexmk) or add latexmk to PATH."
    }
}

$buildDir = Join-Path $scriptDir 'build'
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
Copy-Item -LiteralPath (Join-Path $scriptDir 'references.bib') -Destination (Join-Path $buildDir 'references.bib') -Force

& $latexmk -pdf -interaction=nonstopmode -halt-on-error -file-line-error main.tex
exit $LASTEXITCODE
