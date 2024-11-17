set dotenv-load := true
set unstable := true

mod docs ".just/documentation.just"

[private]
default:
    @just --list --list-submodules

[private]
cog:
    uv run --with cogapp cog -r CONTRIBUTING.md

[private]
fmt:
    @just --fmt
    @just docs fmt

[private]
nox SESSION *ARGS:
    uv run nox --session "{{ SESSION }}" -- "{{ ARGS }}"

bootstrap:
    uv python install
    uv sync --locked

coverage:
    @just nox coverage

lint:
    @just nox lint

lock *ARGS:
    uv lock {{ ARGS }}

test *ARGS:
    @just nox test {{ ARGS }}

testall *ARGS:
    @just nox tests {{ ARGS }}

types *ARGS:
    @just nox types {{ ARGS }}
