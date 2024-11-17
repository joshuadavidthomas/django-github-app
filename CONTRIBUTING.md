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

The repository includes a `Justfile` that provides all common development tasks with a consistent interface. Running `just` without arguments shows all available commands and their descriptions:

<!-- [[[cog
import subprocess
import cog

output_raw = subprocess.run(["just", "--list", "--list-submodules"], stdout=subprocess.PIPE)
output_list = output_raw.stdout.decode("utf-8").split("\n")

cog.outl("""\
```bash
$ just
$ # or explicitly
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
$ # or explicitly
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

Alternatively, any Python package manager that supports installing from `pyproject.toml` ([PEP 621](https://peps.python.org/pep-0621/)) can be used. If not using `uv`, ensure you have Python installed from [python.org](https://www.python.org/).

1. Fork the repository and clone it locally.
2. Use `uv` too bootstrap your development environment:

```bash
uv python install
uv sync --locked
# or
just bootstrap
```

   This will install the correct Python version, create and configure a virtual environment, and install all dependencies.

## Tests

The project uses [`pytest`](https://docs.pytest.org/) for testing and [`nox`](https://nox.thea.codes/) to run the tests in multiple environments.

To run the test suite against the default versions of Python (lower bound of supported versions) and Django (lower bound of LTS versions):

```bash
uv run nox --session test
# or
just test
```

To run the test suite against the entire matrix of supported versions of Python and Django:

```bash
uv run nox --session tests
# or
just testall
```

Both can be passed additional arguments that will be provided to `pytest`:

```bash
uv run nox --session test -- -v --last-failed
uv run nox --session tests -- --failed-first --maxfail=1
# or
just test -v --last-failed
just testall --failed-first --maxfail=1
```
