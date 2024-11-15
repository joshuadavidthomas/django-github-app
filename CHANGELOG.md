# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project attempts to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!--
## [${version}]
### Added - for new features
### Changed - for changes in existing functionality
### Deprecated - for soon-to-be removed features
### Removed - for now removed features
### Fixed - for any bug fixes
### Security - in case of vulnerabilities
[${version}]: https://github.com/joshuadavidthomas/bird/releases/tag/v${version}
-->

## [Unreleased]

### Added

- Added `acreate_from_gh_data`/`create_from_gh_data` manager methods to `Installation` and `Repository` models.
- Added new methods to `Installation` model:
  - `get_gh_client` for retrieving a `GitHubAPI` client preconfigured for an `Installation` instance.
  - `aget_repos`/`get_repos` for retrieving all repositories accessible to an app installation.
- Added `get_gh_client` model method to `Installation` model.
- Added `aget_repos`/`get_repos` model method to `installation`

## [0.1.0]

### Added

- Created initial models for GitHub App integration:
  - `EventLog` to store webhook events
  - `Installation` to manage GitHub App installations and generate access tokens
  - `Repository` to interact with GitHub repositories and track issues
- Created `AsyncWebhookView` to integrate `gidgethub` webhook handling with Django.
- Created webhook event routing system using `gidgethub.routing.Router`.
- Integrated `gidgethub.abc.GitHubAPI` client with `Installation` authentication.

### New Contributors

- Josh Thomas <josh@joshthomas.dev> (maintainer)

[unreleased]: https://github.com/joshuadavidthomas/django-github-app/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/joshuadavidthomas/django-github-app/releases/tag/v0.1.0
