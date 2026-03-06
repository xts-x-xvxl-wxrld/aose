$ErrorActionPreference = "Stop"

function Run-PythonFallback {
    Write-Host "Docker is not available. Falling back to python local verification."

    if (Test-Path "uv.lock") {
        Write-Host "uv.lock found."
        uv sync
        $runPrefix = "uv run "
    } elseif (Test-Path "pyproject.toml") {
        Write-Host "pyproject.toml found."
        python -m pip install -e .
        $runPrefix = ""
    } else {
        Write-Host "Using requirements files."
        if (Test-Path "requirements.txt") {
            python -m pip install -r requirements.txt
        } else {
            if (Test-Path "api\requirements.txt") { python -m pip install -r api\requirements.txt }
            if (Test-Path "api\requirements-dev.txt") { python -m pip install -r api\requirements-dev.txt }
            if (Test-Path "worker\requirements.txt") { python -m pip install -r worker\requirements.txt }
            if (Test-Path "worker\requirements-dev.txt") { python -m pip install -r worker\requirements-dev.txt }
        }
        $runPrefix = ""
    }

    $env:PYTHONPATH = "api;worker"
    $hasErrors = $false

    if ($runPrefix -eq "uv run ") {
        uv run python -m ruff check api worker
        if ($LASTEXITCODE -ne 0) { $hasErrors = $true }
        uv run python -m ruff format --check api worker
        if ($LASTEXITCODE -ne 0) { $hasErrors = $true }
        uv run python -m pytest -q api worker
        if ($LASTEXITCODE -ne 0) { $hasErrors = $true }
    } else {
        python -m ruff check api worker
        if ($LASTEXITCODE -ne 0) { $hasErrors = $true }
        python -m ruff format --check api worker
        if ($LASTEXITCODE -ne 0) { $hasErrors = $true }
        python -m pytest -q api worker
        if ($LASTEXITCODE -ne 0) { $hasErrors = $true }
    }

    if ($hasErrors) {
        Write-Host "Verification Failed."
        exit 1
    } else {
        Write-Host "Verification Passed."
    }
}

# Check for Docker
$dockerExists = Get-Command "docker" -ErrorAction SilentlyContinue

if ($dockerExists) {
    Write-Host "Docker found. Running via docker compose..."
    try {
        docker compose up -d --build
    } catch {
        Write-Host "Docker compose failed."
        exit 1
    }

    Write-Host "Waiting for API health at http://localhost:8000/healthz..."
    $maxRetries = 30
    $retryCount = 0
    $healthOk = $false

    while ($retryCount -lt $maxRetries) {
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:8000/healthz" -UseBasicParsing -ErrorAction Stop
            if ($resp.Content -match '"status"\s*:\s*"ok"') {
                $healthOk = $true
                Write-Host "API is healthy!"
                break
            }
        } catch {
            # Ignore and retry
        }
        Write-Host "Waiting... (Attempt $($retryCount + 1)/$maxRetries)"
        Start-Sleep -Seconds 2
        $retryCount++
    }

    if (-not $healthOk) {
        Write-Host "Error: API failed healthcheck."
        exit 1
    }

    Write-Host "Running verification commands..."
    $hasErrors = $false

    try { docker compose exec api python -m ruff check .; docker compose exec worker python -m ruff check . } catch { $hasErrors = $true }
    try { docker compose exec api python -m ruff format --check .; docker compose exec worker python -m ruff format --check . } catch { $hasErrors = $true }
    try { docker compose exec api python -m pytest -q; docker compose exec worker python -m pytest -q } catch { $hasErrors = $true }

    if ($hasErrors) {
        Write-Host "Verification Failed."
        exit 1
    } else {
        Write-Host "Verification Passed."
    }

} else {
    Run-PythonFallback
}
