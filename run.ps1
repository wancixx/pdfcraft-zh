# pdfcraft-zh launcher -- Windows (PowerShell)
#
# Finds a Python 3.8+ (or explains how to install one), then hands over to
# pdfcraft-zh.py. The main script uses the standard library only, so any
# Python 3 on the system will do: no pip, no virtualenv.

$ErrorActionPreference = 'Stop'

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Main = Join-Path $Here 'pdfcraft-zh.py'

function Say  ($m) { Write-Host $m }
function Ok   ($m) { Write-Host $m -ForegroundColor Green }
function Warn ($m) { Write-Host $m -ForegroundColor Yellow }
function Die  ($m) { Write-Host ""; Write-Host "error: $m" -ForegroundColor Red; exit 1 }

function Find-Python {
    foreach ($name in @('python', 'python3', 'py')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        try {
            & $cmd.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $cmd.Source }
        } catch { }
    }
    return $null
}

function Install-Hint {
    Say ""
    Warn "Python 3.8 or newer was not found."
    Say ""
    Say "There are two ways to install it:"
    Say ""
    Say "  1) With winget (built into Windows 10/11, easiest):"
    Say "     winget install Python.Python.3.12"
    Say "     Close this window and run run.bat again afterwards."
    Say ""
    Say "  2) Download the installer from https://www.python.org/downloads/"
    Say "     and tick 'Add python.exe to PATH' during setup."
    Say ""
}

Say ""
Say "pdfcraft-zh"
Say "  Adds to PdfCraft: system CJK fonts / four UI languages / Chinese OCR"
Say ""

$py = Find-Python
if (-not $py) {
    Install-Hint
    exit 1
}

Ok "  ✓ Using Python: $py"
& $py $Main @args
exit $LASTEXITCODE
