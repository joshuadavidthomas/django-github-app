#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "bumpver",
#     "typer",
# ]
# ///
from __future__ import annotations

import re
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated
from typing import Any

import typer
from typer import Option


class CommandRunner:
    def run_command(self, command: str) -> tuple[bool, str]:
        print(f"about to run command: {command}")
        try:
            output = subprocess.check_output(
                command, shell=True, text=True, stderr=subprocess.STDOUT
            ).strip()
            return True, output
        except subprocess.CalledProcessError as e:
            return False, e.output

    def _build_command_args(self, **params: Any) -> str:
        args = []
        for key, value in params.items():
            key = key.replace("_", "-")
            if isinstance(value, bool) and value:
                args.append(f"--{key}")
            elif value is not None:
                args.extend([f"--{key}", str(value)])
        return " ".join(args)

    def run(self, cmd: str, name: str, *args: str, **params: Any) -> str:
        command_parts = [cmd, name]
        command_parts.extend(args)
        if params:
            command_parts.append(self._build_command_args(**params))
        success, output = self.run_command(" ".join(command_parts))
        if not success:
            print(f"{cmd} failed: {output}", file=sys.stderr)
            raise typer.Exit(1)
        return output


_runner = CommandRunner()


def bumpver(name: str, *args: str, **params: Any) -> str:
    return _runner.run("bumpver", name, *args, **params)


def git(name: str, *args: str, **params: Any) -> str:
    return _runner.run("git", name, *args, **params)


def gh(name: str, *args: str, **params: Any) -> str:
    return _runner.run("gh", name, *args, **params)


def update_CHANGELOG(new_version: str) -> None:
    repo_url = git("remote", "get-url", "origin").strip().replace(".git", "")
    changelog = Path("CHANGELOG.md")

    content = changelog.read_text()

    content = re.sub(
        r"## \[Unreleased\]",
        f"## [{new_version}]",
        content,
        count=1,
    )
    content = re.sub(
        rf"## \[{new_version}\]",
        f"## [Unreleased]\n\n## [{new_version}]",
        content,
        count=1,
    )
    content += f"[{new_version}]: {repo_url}/releases/tag/v{new_version}\n"
    content = re.sub(
        r"\[unreleased\]: .*\n",
        f"[unreleased]: {repo_url}/compare/v{new_version}...HEAD\n",
        content,
        count=1,
    )

    changelog.write_text(content)

    git("add", ".")
    git("commit", "-m", f"update CHANGELOG for version {new_version}")


class Version(str, Enum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


class Tag(str, Enum):
    DEV = "dev"
    ALPHA = "alpha"
    BETA = "beta"
    RC = "rc"
    FINAL = "final"


def main(
    version: Annotated[
        Version, Option("--version", "-v", help="The tag to add to the new version")
    ],
    tag: Annotated[Tag, Option("--tag", "-t", help="The tag to add to the new version")]
    | None = None,
):
    new_version = re.search(
        r"New Version: (.+)", bumpver("update", dry=True, tag=tag, **{version: True})
    )
    if new_version is None:
        new_version = typer.prompt(
            "Failed to get the new version from `bumpver`. Please enter it manually"
        )
    else:
        new_version = new_version.group(1)
    release_branch = f"release-v{new_version}"
    git("checkout", "-b", release_branch)
    bumpver("update", tag=tag, **{version: True})
    title = git("log", "-1", "--pretty=%s")
    update_CHANGELOG(new_version)
    git("push", "--set-upstream", "'origin'", f"'{release_branch}'")
    gh(
        "pr",
        "create",
        "--base 'main'",
        f"--head '{release_branch}'",
        f" --title '{title}'",
    )


if __name__ == "__main__":
    typer.run(main)
