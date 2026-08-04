#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

if ! command -v latexmk >/dev/null 2>&1; then
    echo "latexmk was not found." >&2
    echo "Install the Ubuntu dependencies with:" >&2
    echo "  sudo apt install latexmk texlive-latex-extra texlive-science" >&2
    exit 127
fi

mkdir -p build
cp references.bib build/references.bib

latexmk -pdf -interaction=nonstopmode -halt-on-error -file-line-error main.tex
