set unstable := true

justfile := justfile_directory() + "/.just/documentation.just"

[private]
default:
    @just --list --justfile {{ justfile }}

[private]
fmt:
    @just --fmt --justfile {{ justfile }}

# Build documentation using Sphinx
[no-cd]
build LOCATION="docs/_build/html":
    @just cog
    uv run --extra docs sphinx-build docs {{ LOCATION }}

# Serve documentation locally
[no-cd]
serve PORT="8000":
    #!/usr/bin/env sh
    HOST="localhost"
    if [ -f "/.dockerenv" ]; then
        HOST="0.0.0.0"
    fi
    just cog
    uv run --extra docs sphinx-autobuild docs docs/_build/html --host "$HOST" --port {{ PORT }}
