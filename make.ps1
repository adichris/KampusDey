# PowerShell equivalent of the Makefile for Windows: .\make.ps1 <target>
param([Parameter(Position = 0)][string]$Target = "help")

$ErrorActionPreference = "Stop"
$Py = ".\.venv\Scripts\python.exe"

function Manage { & $Py manage.py @args; if ($LASTEXITCODE) { exit $LASTEXITCODE } }
function Run { & $args[0] @($args | Select-Object -Skip 1); if ($LASTEXITCODE) { exit $LASTEXITCODE } }

switch ($Target) {
    "install" {
        python -m venv .venv
        Run $Py -m pip install -r requirements-dev.txt
        npm install; npm run vendor; npm run build:css
    }
    "run" { Manage runserver }
    "migrate" { Manage migrate; Manage createcachetable }
    "makemigrations" { Manage makemigrations }
    "test" { Run $Py -m pytest }
    "test-fast" { Run $Py -m pytest apps/core apps/accounts apps/listings -x }
    "lint" { Run $Py -m ruff check .; Run $Py -m ruff format --check . }
    "fmt" { Run $Py -m ruff format .; Run $Py -m ruff check --fix . }
    "tailwind" { npm run build:css }
    "tailwind-watch" { npm run watch:css }
    "vendor" { npm run vendor }
    "seed" { Manage seed_locations }
    "import-locations" { Manage import_locations }
    "import-external" { Manage import_external }
    "seed-demo" { Manage seed_demo }
    "periodic" { Manage run_periodic --loop }
    "shell" { Manage shell }
    "check" { Manage check; Manage makemigrations --check --dry-run }
    "up" { docker compose up -d --build }
    "down" { docker compose down }
    default {
        Write-Output "Targets: install run migrate makemigrations test test-fast lint fmt tailwind tailwind-watch vendor seed import-locations import-external seed-demo periodic shell check up down"
    }
}
