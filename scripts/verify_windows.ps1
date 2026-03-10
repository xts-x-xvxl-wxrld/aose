$ErrorActionPreference = "Stop"

function Invoke-NativeStep {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Host $FailureMessage
        exit $LASTEXITCODE
    }
}

function Start-DockerDesktopIfNeeded {
    $dockerInfo = Get-Command "docker" -ErrorAction SilentlyContinue
    if (-not $dockerInfo) {
        return $false
    }

    docker info | Out-Null
    if ($LASTEXITCODE -eq 0) {
        return $true
    }

    $dockerDesktopPath = Join-Path $Env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $dockerDesktopPath)) {
        Write-Host "Docker Desktop executable not found at $dockerDesktopPath"
        return $false
    }

    Write-Host "Docker daemon is not reachable. Starting Docker Desktop..."
    Start-Process -FilePath $dockerDesktopPath | Out-Null

    for ($attempt = 1; $attempt -le 30; $attempt++) {
        Start-Sleep -Seconds 2
        docker info | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Docker daemon is available."
            return $true
        }
    }

    Write-Host "Docker Desktop did not become ready in time."
    return $false
}

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
$dockerUsable = $false

if ($dockerExists) {
    $dockerUsable = Start-DockerDesktopIfNeeded
    if (-not $dockerUsable) {
        Write-Host "Docker is installed but the daemon is not accessible. Falling back to python local verification."
    }
}

if ($dockerUsable) {
    Write-Host "Docker found. Running via docker compose..."
    Invoke-NativeStep -Command { docker compose up -d --build } -FailureMessage "Docker compose failed."

    $runningApi = docker compose ps --services --filter status=running api
    $apiPsExitCode = $LASTEXITCODE
    if ($apiPsExitCode -ne 0 -or -not ($runningApi -contains "api")) {
        Write-Host "API container is not running after docker compose up."
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
    Invoke-NativeStep -Command { docker compose exec api python -m ruff check . } -FailureMessage "API lint failed."
    Invoke-NativeStep -Command { docker compose exec worker python -m ruff check . } -FailureMessage "Worker lint failed."
    Invoke-NativeStep -Command { docker compose exec api python -m ruff format --check . } -FailureMessage "API format check failed."
    Invoke-NativeStep -Command { docker compose exec worker python -m ruff format --check . } -FailureMessage "Worker format check failed."
    Invoke-NativeStep -Command { docker compose exec api python -m pytest -q } -FailureMessage "API tests failed."
    Invoke-NativeStep -Command { docker compose exec worker python -m pytest -q } -FailureMessage "Worker tests failed."

    Write-Host "Verification Passed."

} else {
    Run-PythonFallback
}
