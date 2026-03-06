<#
.SYNOPSIS
AOSE wrapper script for Windows. Replaces make.

.DESCRIPTION
Provides subcommands for local dev lifecycle.
Calls docker compose from repo root.

.EXAMPLE
.\scripts\dev.ps1 up
#>

param (
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateSet("up", "down", "ps", "logs", "health", "migrate", "test", "lint")]
    [string]$Command
)

$ErrorActionPreference = "Stop"

# Move to repo root
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $RepoRoot
Set-Location $RepoRoot

switch ($Command) {
    "up" {
        docker compose up -d
    }
    "down" {
        docker compose down -v
    }
    "ps" {
        docker compose ps
    }
    "logs" {
        docker compose logs -f
    }
    "health" {
        Invoke-WebRequest -Uri "http://localhost:8000/healthz" -UseBasicParsing | Select-Object StatusCode, StatusDescription
    }
    "migrate" {
        docker compose exec api alembic upgrade head
    }
    "test" {
        Write-Host "Running tests in container per Windows boundary rule..."
        # We run in api container and worker container
        docker compose exec api pytest -q .
        docker compose exec worker pytest -q .
    }
    "lint" {
        Write-Host "Running linting in container per Windows boundary rule..."
        docker compose exec api ruff check .
        docker compose exec api ruff format --check .
        docker compose exec worker ruff check .
        docker compose exec worker ruff format --check .
    }
}
