# AI Outbound Support Engine (AOSE)

## Local Development
- Boot stack: `make dev`
- Run tests: `make test`
- Lint: `make lint`
- Format: `make fmt`

## Verification & CI Determinism
To catch formatting and linting drift before GitHub Actions CI, it is highly recommended to install the pre-commit hooks:
```bash
pip install pre-commit
pre-commit install
```

The canonical local verification scripts mirror the CI pipeline exactly:
- **Windows**: `.\scripts\verify_windows.ps1`
- **Linux/Mac**: `./scripts/verify_docker.sh`
Or run `make fmt-check lint test` if `make` is available.
