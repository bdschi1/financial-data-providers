# Contributing

## Development Setup

```bash
git clone https://github.com/bdschi1/financial-data-providers.git
cd financial-data-providers
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Code Style

- Lint with `ruff check .`
- Format with `ruff format .`
- Line length limit: 100 (configured in pyproject.toml)
- Type hints encouraged

## Testing

```bash
pytest tests/ -v
```

## Adding a New Provider

1. Create `bds_data_providers/{name}.py` implementing `DataProvider` (Polars ABC)
2. Create `bds_data_providers/{name}_market.py` implementing `MarketDataProvider` (dict/pandas ABC)
3. Add an `is_available()` function in each module for auto-detection
4. Register the provider in `factory.py` (`_PROVIDER_REGISTRY`) and `market_factory.py` (`_MARKET_PROVIDER_REGISTRY`)
5. Re-export classes in `__init__.py` and update `__all__`
6. Add optional dependency group in `pyproject.toml`
7. Add tests in `tests/`

## Pull Requests

1. Create a feature branch from `main`
2. Make focused, single-purpose commits
3. Ensure all tests pass before submitting
4. Open a PR with a clear description of changes
