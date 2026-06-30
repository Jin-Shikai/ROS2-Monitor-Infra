$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$gitPerlBin = 'C:\Program Files\Git\usr\bin'
if (Test-Path -LiteralPath (Join-Path $gitPerlBin 'perl.exe')) {
    $env:Path = "$gitPerlBin;$env:Path"
}

$miktexBin = 'C:\Users\Probe\AppData\Local\Programs\MiKTeX\miktex\bin\x64'
$latexmk = Join-Path $miktexBin 'latexmk.exe'
if (-not (Test-Path -LiteralPath $latexmk)) {
    $latexmk = 'latexmk'
}

New-Item -ItemType Directory -Force -Path (Join-Path $scriptDir 'build') | Out-Null
Copy-Item -LiteralPath (Join-Path $scriptDir 'references.bib') -Destination (Join-Path $scriptDir 'build\references.bib') -Force
& $latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
exit $LASTEXITCODE
