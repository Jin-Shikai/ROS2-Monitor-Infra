$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $scriptDir

try {
    $gitPerlBin = 'C:\Program Files\Git\usr\bin'
    if (Test-Path -LiteralPath (Join-Path $gitPerlBin 'perl.exe')) {
        $env:Path = "$gitPerlBin;$env:Path"
    }

    $miktexBin = 'C:\Users\Probe\AppData\Local\Programs\MiKTeX\miktex\bin\x64'
    $latexmk = Join-Path $miktexBin 'latexmk.exe'
    if (-not (Test-Path -LiteralPath $latexmk)) {
        $latexmk = 'latexmk'
    }

    $texFile = Join-Path $scriptDir 'pseudocode.tex'
    if (-not (Test-Path -LiteralPath $texFile)) {
        throw "Missing TeX source: $texFile"
    }

    & $latexmk -pdf -interaction=nonstopmode -halt-on-error -file-line-error pseudocode.tex
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
