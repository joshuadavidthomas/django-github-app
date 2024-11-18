# Contributing

All contributions are welcome! Besides code contributions, this includes things like documentation improvements, bug reports, and feature requests.

You should first check if there is a [GitHub issue](https://github.com/joshuadavidthomas/django-github-app/issues) already open or related to what you would like to contribute. If there is, please comment on that issue to let others know you are working on it. If there is not, please open a new issue to discuss your contribution.

Not all contributions need to start with an issue, such as typo fixes in documentation or version bumps to Python or Django that require no internal code changes, but generally, it is a good idea to open an issue first.

We adhere to Django's Code of Conduct in all interactions and expect all contributors to do the same. Please read the [Code of Conduct](https://www.djangoproject.com/conduct/) before contributing.

## Requirements

- [uv](https://github.com/astral-sh/uv) - Modern Python toolchain that handles:
  - Python version management and installation
  - Virtual environment creation and management
  - Fast, reliable dependency resolution and installation
  - Reproducible builds via lockfile
- [direnv](https://github.com/direnv/direnv) (Optional) - Automatic environment variable loading
- [just](https://github.com/casey/just) (Optional) - Command runner for development tasks

### `Justfile`

The repository includes a `Justfile` that provides all common development tasks with a consistent interface. Running `just` without arguments shows all available commands and their descriptions.

<!-- [[[cog
import subprocess
import cog

output_raw = subprocess.run(["just", "--list", "--list-submodules"], stdout=subprocess.PIPE)
output_list = output_raw.stdout.decode("utf-8").split("\n")

cog.outl("""\
```bash
$ just
$ # just --list --list-submodules
""")

for i, line in enumerate(output_list):
    if not line:
        continue
    cog.out(line)
    if i < len(output_list):
        cog.out("\n")

cog.out("```")
]]] -->
```bash
$ just
$ # just --list --list-submodules

Available recipes:
    bootstrap
    coverage
    lint
    lock *ARGS
    test *ARGS
    testall *ARGS
    types *ARGS
    docs:
        build LOCATION="docs/_build/html" # Build documentation using Sphinx
        serve PORT="8000"                 # Serve documentation locally
```
<!-- [[[end]]] -->

All commands below will contain the full command as well as its `just` counterpart.

## Setup

The following instructions will use `uv` and assume a Unix-like operating system (Linux or macOS).

Windows users will need to adjust commands accordingly, though the core workflow remains the same.

Alternatively, any Python package manager that supports installing from `pyproject.toml` ([PEP 621](https://peps.python.org/pep-0621/)) can be used. If not using `uv`, ensure you have Python installed from [python.org](https://www.python.org/) or another source such as [`pyenv`](https://github.com/pyenv/pyenv).

1. Fork the repository and clone it locally.

2. Use `uv` to bootstrap your development environment.

   ```bash
   uv python install
   uv sync --locked
   # just bootstrap
   ```

   This will install the correct Python version, create and configure a virtual environment, and install all dependencies.

## Tests

The project uses [`pytest`](https://docs.pytest.org/) for testing and [`nox`](https://nox.thea.codes/) to run the tests in multiple environments.

To run the test suite against the default versions of Python (lower bound of supported versions) and Django (lower bound of LTS versions):

```bash
uv run nox --session test
# just test
```

To run the test suite against the entire matrix of supported versions of Python and Django:

```bash
uv run nox --session tests
# just testall
```

Both can be passed additional arguments that will be provided to `pytest`.

```bash
uv run nox --session test -- -v --last-failed
uv run nox --session tests -- --failed-first --maxfail=1
# just test -v --last-failed
# just testall --failed-first --maxfail=1
```

### Coverage

The project uses [`coverage.py`](https://github.com/nedbat/coverage.py) to measure code coverage and aims to maintain 100% coverage across the codebase.

To run the test suite and measure code coverage:

```bash
uv run nox --session coverage
# just coverage
```

All pull requests must include tests to maintain 100% coverage. Coverage configuration can be found in the `[tools.coverage.*]` sections of [`pyproject.toml`](pyproject.toml).

### Integration Tests

Integration tests in [`tests/integration`](tests/integration) verify actual interactions with GitHub's API and webhooks. These tests are skipped by default and require:

- A GitHub App in your account
- Environment variables configured with the App's credentials

To enable integration tests, pass `--integration` to any test command:

```bash
uv run nox --session test -- --integration
# just test --integration
```

#### Setting up a Test GitHub App

1. Create a new GitHub App.

   - Go to GitHub Developer Settings > GitHub Apps > New GitHub App
   - Name: `@<username> - django-github-app tests` (must be unique on GitHub, max 34 characters)
   - Homepage URL: Your fork's URL (e.g., `https://github.com/<username>/django-github-app`)
   - Webhooks: Disable by unchecking "Active" (no webhook tests currently implemented)
   - Permissions:
     - Repository: Metadata (Read-only)
   - Installation: "Only on this account"

2. After creation, collect these values:

   - App ID (from app settings)
   - Client ID (from app settings)
   - Private key (generate and download)
   - Installation ID (from URL after installing: `https://github.com/settings/installations/<ID>`)

3. Configure environment variables.

   Using direnv (recommended):

   ```bash
   cp .env.example .env
   ```

   Edit the new `.env` file with the values collected above.

   Or manually export:

   ```bash
   export TEST_ACCOUNT_NAME="<username>"
   # etc...
   ```

See [`.env.example`](.env.example) for all required variables.

#### Setting up CI Integration Tests

If you want integration tests to run in CI on your fork:

1. Go to your fork's repository settings on GitHub

2. Under "Environments", create a new environment named `integration`

3. Add the following secrets and variables to the environment:

   - Secrets
     - `TEST_PRIVATE_KEY`
     - `TEST_WEBHOOK_SECRET`
   - Variables
     - `TEST_ACCOUNT_NAME`
     - `TEST_ACCOUNT_TYPE`
     - `TEST_APP_ID`
     - `TEST_CLIENT_ID`
     - `TEST_INSTALLATION_ID`
     - `TEST_NAME`

> [!NOTE]
> Integration tests in CI will only run with access to these environment secrets. This is a security feature - fork PRs cannot access these secrets unless explicitly granted by repository maintainers.

#### Security Considerations

The integration test setup is designed to be secure:

- The test GitHub App requires minimal permissions (read-only metadata access)
- It's installed only on your personal account
- In CI, tests run in a protected GitHub Environment with restricted secret access
- Fork PRs cannot access integration test secrets (managed automatically by GitHub Actions)

## Linting and Formatting

This project enforces code quality standards using [`pre-commit`](https://github.com/pre-commit/pre-commit).

To run all formatters and linters:

```bash
uv run nox --session lint
# just lint
```

The following checks are run:

- [ruff](https://github.com/astral-sh/ruff) - Fast Python linter and formatter
- Code formatting for Python files in documentation ([blacken-docs](https://github.com/adamchainz/blacken-docs))
- Django compatibility checks ([django-upgrade](https://github.com/adamchainz/django-upgrade))
- TOML and YAML validation
- Basic file hygiene (trailing whitespace, file endings)

To enable pre-commit hooks after cloning:

```bash
uv run --with pre-commit pre-commit install
```

Configuration for these tools can be found in:

- [`.pre-commit-config.yaml`](.pre-commit-config.yaml) - Pre-commit hook configuration
- [`pyproject.toml`](pyproject.toml) - Ruff and other tool settings

## Continuous Integration

This project uses GitHub Actions for CI/CD. The workflows can be found in [`.github/workflows/`](.github/workflows/).

- [`test.yml`](.github/workflows/test.yml) - Runs on pushes to the `main` branch and on all PRs
  - Tests across Python/Django version matrix
  - Static type checking
  - Coverage reporting
- [`release.yml`](.github/workflows/release.yml) - Runs on GitHub release creation
  - Runs the [`test.yml`](.github/workflows/test.yml) workflow
  - Builds package
  - Publishes to PyPI

PRs must pass all CI checks before being merged.
