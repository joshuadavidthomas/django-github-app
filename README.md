# django-github-app

<!-- [[[cog
import subprocess
import cog

from noxfile import DJ_VERSIONS
from noxfile import PY_VERSIONS

cog.outl("[![PyPI](https://img.shields.io/pypi/v/django-github-app)](https://pypi.org/project/django-github-app/)")
cog.outl("![PyPI - Python Version](https://img.shields.io/pypi/pyversions/django-github-app)")
cog.outl(f"![Django Version](https://img.shields.io/badge/django-{'%20%7C%20'.join(DJ_VERSIONS)}-%2344B78B?labelColor=%23092E20)")
]]] -->
[![PyPI](https://img.shields.io/pypi/v/django-github-app)](https://pypi.org/project/django-github-app/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/django-github-app)
![Django Version](https://img.shields.io/badge/django-4.2%20%7C%205.1%20%7C%205.2%20%7C%20main-%2344B78B?labelColor=%23092E20)
<!-- [[[end]]] -->

A Django toolkit providing the batteries needed to build GitHub Apps - from webhook handling to API integration.

Built on [gidgethub](https://github.com/gidgethub/gidgethub) and [httpx](https://github.com/encode/httpx), django-github-app handles the boilerplate of GitHub App development. Features include webhook event routing and storage, API client with automatic authentication, and models for managing GitHub App installations, repositories, and webhook event history.

Fully supports both sync (WSGI) and async (ASGI) Django applications.

## Projects using django-github-app

- [psf/clabot](https://github.com/psf/clabot)

Are you using django-github-app in a production application? Open a PR to add it to this list!

## Requirements

<!-- [[[cog
import subprocess
import cog

from noxfile import DJ_VERSIONS
from noxfile import PY_VERSIONS

cog.outl(f"- Python {', '.join([version for version in PY_VERSIONS])}")
cog.outl(f"- Django {', '.join([version for version in DJ_VERSIONS if version != 'main'])}")
]]] -->
- Python 3.10, 3.11, 3.12, 3.13
- Django 4.2, 5.1, 5.2
<!-- [[[end]]] -->

## Installation

1. Install the package from [PyPI](https://pypi.org/project/django-github-app).

    ```bash
    python -m pip install django-github-app

    # or if you like the new hotness

    uv add django-github-app
    uv sync
    ```

2. Add the app to `INSTALLED_APPS` in your Django project's `DJANGO_SETTINGS_MODULE`.

    ```python
    INSTALLED_APPS = [
        "django_github_app",
    ]
    ```

3. Run the `migrate` management command to add django-github-app's models to your database.

   ```bash
   python manage.py migrate

   # or for those living on the bleeding edge

   uv run manage.py migrate
   ```

4. Add django-github-app's webhook view to your Django project's urls.

   For Django projects running on ASGI, use `django_github_app.views.AsyncWebhookView`:

   ```python
   from django.urls import path

   from django_github_app.views import AsyncWebhookView

   urlpatterns = [
       path("gh/", AsyncWebhookView.as_view()),
   ]
   ```

   For traditional Django projects running on WSGI, use `django_github_app.views.SyncWebhookView`:

   ```python
   from django.urls import path

   from django_github_app.views import SyncWebhookView

   urlpatterns = [
       path("gh/", SyncWebhookView.as_view()),
   ]
   ```

> [!IMPORTANT]
> Make sure your `GITHUB_APP["WEBHOOK_TYPE"]` setting matches your view choice:
>
> - Use `"async"` with `AsyncWebhookView`
> - Use `"sync"` with `SyncWebhookView`

5. Setup your GitHub App and configure django-github-app using your GitHub App's information.

   You will need the following information from your GitHub App:

    - App ID
    - Client ID
    - Name
    - Private Key (either the file object or the contents)
    - Webhook Secret
    - Webhook URL

   All examples below use [environs](https://github.com/sloria/environs) to load the values from an `.env` file. Adjust the code to your preferred way of loading Django settings.

> [!NOTE]
> All examples will use the private key contents loaded directly from environment. To use a key file instead:
>
> ```python
> import environs
>
> env = environs.Env()
> env.read_env()
>
> GITHUB_APP = {
>     "PRIVATE_KEY": env.path("GITHUB_PRIVATE_KEY_PATH"),
> }
> ```
>
> django-github-app will automatically detect if `GITHUB_APP["PRIVATE_KEY"]` is a path and load the file contents. For more information, see the [`PRIVATE_KEY`](#private_key) section in the [Configuration](#configuration) documentation below.

### GitHub App Setup

After completing the [Installation](#installation) steps above, you will need to set up your GitHub App using the information from Step 5 above.

Choose the appropriate setup method based on your situation:

- **[Create a New GitHub App](#create-a-new-github-app)**: If you're setting up a fresh GitHub App
- **[Use an Existing GitHub App](#use-an-existing-github-app-and-installation)**: If your GitHub App is already installed on organizations/repositories

> [!IMPORTANT]
> django-github-app needs to create `Installation` and `Repository` models in your database to track where your GitHub App is installed. How this happens depends on your setup method:
>
> - **New GitHub App**: When you install the app for the first time, GitHub sends an `installation.created` webhook event. django-github-app automatically creates the necessary models when it receives this event.
> - **Existing GitHub App**: If the app is already installed, no `installation.created` webhook event is sent. django-github-app will automatically create the models when it receives the first `installation_repositories` event (e.g., when repositories are added/removed). Alternatively, you can use the `github import-app` management command to import the installation immediately.

#### Create a New GitHub App

1. Register a new GitHub App, following [these instructions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app) from the GitHub Docs. For a more detailed tutorial, there is also [this page](https://docs.github.com/en/apps/creating-github-apps/writing-code-for-a-github-app/building-a-github-app-that-responds-to-webhook-events) -- in particular the section on [Setup](https://docs.github.com/en/apps/creating-github-apps/writing-code-for-a-github-app/building-a-github-app-that-responds-to-webhook-events#setup).

   For the Private Key, you will be able to use either the file contents or the file itself to authenticate with GitHub, as described in the note above.

   For the Webhook URL, use the endpoint you configured in step 4 (e.g., `<your project's base url>/gh/`).

2. Configure your Django settings by adding the following dictionary to your `DJANGO_SETTINGS_MODULE`, filling in the values from the previous step.

   ```python
   import environs

   env = environs.Env()
   env.read_env()

   GITHUB_APP = {
       "APP_ID": env.int("GITHUB_APP_ID"),
       "CLIENT_ID": env.str("GITHUB_CLIENT_ID"),
       "NAME": env.str("GITHUB_NAME"),
       "PRIVATE_KEY": env.str("GITHUB_PRIVATE_KEY"),
       "WEBHOOK_SECRET": env.str("GITHUB_WEBHOOK_SECRET"),
       "WEBHOOK_TYPE": "async",  # Use "async" for ASGI projects or "sync" for WSGI projects
   }
   ```

3. Install the GitHub App on your account.

   - Go to your GitHub App's settings
   - Click "Install App"
   - Select the account to install it on
   - Choose which repositories to give it access to

   When you install the app **for the first time**, django-github-app will automatically create the necessary `Installation` and `Repository` models when it receives the `installation.created` webhook event.

#### Use an Existing GitHub App and Installation

If your GitHub App is already installed on organizations/repositories, the `installation.created` webhook event won't be sent when you connect django-github-app to your existing app. django-github-app will automatically create the necessary models when it receives the first webhook event that includes installation data (such as `installation_repositories`).

However, if you want to import the installation immediately without waiting for a webhook event, you can use the management command below.

1. Collect your existing app and installation's information.

   - All GitHub App information and credentials listed above in step 5 of [Installation](#instalation)
     - Make sure the Webhook URL matches the endpoint configured in step 4 of [Installation](#installation)
   - Account type where installed (`org` or `user`)
   - Account name (username or organization name)
   - Installation ID (e.g. `https://github.com/settings/installations/<ID>` for an user installation)

2. Configure your Django settings by adding the following dictionary to your `DJANGO_SETTINGS_MODULE`, filling in the values from your existing GitHub App.

   ```python
   import environs

   env = environs.Env()
   env.read_env()

   GITHUB_APP = {
       "APP_ID": env.int("GITHUB_APP_ID"),
       "CLIENT_ID": env.str("GITHUB_CLIENT_ID"),
       "NAME": env.str("GITHUB_NAME"),
       "PRIVATE_KEY": env.str("GITHUB_PRIVATE_KEY"),
       "WEBHOOK_SECRET": env.str("GITHUB_WEBHOOK_SECRET"),
       "WEBHOOK_TYPE": "async",  # Use "async" for ASGI projects or "sync" for WSGI projects
   }
   ```

3. Import your existing GitHub App by using the `github import-app` management command to create the necessary `Installation` and `Repository` models.

   ```bash
   python manage.py github import-app --type user --name <username> --installation-id 123456

   # or for you thrill seekers and early adopters

   uv run manage.py github import-app --type user --name <username> --installation-id 123456
   ```

> [!NOTE]
> After importing, django-github-app will handle future webhook events normally, including repository additions/removals via the `installation_repositories` event.

## Getting Started

### Webhook Events

django-github-app provides a router-based system for handling GitHub webhook events, built on top of [gidgethub](https://github.com/gidgethub/gidgethub). The router matches incoming webhooks to your handler functions based on the event type and optional action.

To start handling GitHub webhooks, create your event handlers in a new file (e.g., `events.py`) within your Django app.

For ASGI projects using `django_github_app.views.AsyncWebhookView`:

```python
# your_app/events.py
from django_github_app.routing import GitHubRouter

gh = GitHubRouter()

# Handle any issue event
@gh.event("issues")
async def handle_issue(event, gh, *args, **kwargs):
    issue = event.data["issue"]
    labels = []

    # Add labels based on issue title
    title = issue["title"].lower()
    if "bug" in title:
        labels.append("bug")
    if "feature" in title:
        labels.append("enhancement")

    if labels:
        await gh.post(issue["labels_url"], data=labels)


# Handle specific issue actions
@gh.event("issues", action="opened")
async def welcome_new_issue(event, gh, *args, **kwargs):
    """Post a comment when a new issue is opened"""
    url = event.data["issue"]["comments_url"]
    await gh.post(
        url, data={"body": "Thanks for opening an issue! We'll take a look soon."}
    )
```

For WSGI projects using `django_github_app.views.SyncWebhookView`:

```python
# your_app/events.py
from django_github_app.routing import GitHubRouter

gh = GitHubRouter()

# Handle any issue event
@gh.event("issues")
def handle_issue(event, gh, *args, **kwargs):
    issue = event.data["issue"]
    labels = []

    # Add labels based on issue title
    title = issue["title"].lower()
    if "bug" in title:
        labels.append("bug")
    if "feature" in title:
        labels.append("enhancement")

    if labels:
        gh.post(issue["labels_url"], data=labels)


# Handle specific issue actions
@gh.event("issues", action="opened")
def welcome_new_issue(event, gh, *args, **kwargs):
    """Post a comment when a new issue is opened"""
    url = event.data["issue"]["comments_url"]
    gh.post(url, data={"body": "Thanks for opening an issue! We'll take a look soon."})
```

> [!IMPORTANT]
> Choose either async or sync handlers based on your webhook view - async handlers for `AsyncWebhookView`, sync handlers for `SyncWebhookView`. Mixing async and sync handlers is not supported.

In these examples, we automatically label issues based on their title and post a welcome comment on newly opened issues. The router ensures each webhook is directed to the appropriate handler based on the event type and action.

Each handler receives two arguments:

- `event`: A `gidgethub.sansio.Event` containing the webhook payload
- `gh`: A GitHub API client for making API calls (`AsyncGitHubAPI` for async handlers, `SyncGitHubAPI` for sync handlers)

To activate your webhook handlers, import them in your app's `AppConfig.ready()` method, similar to how Django signals are registered.

```python
# your_app/apps.py
from django.apps import AppConfig


class YourAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "your_app"

    def ready(self):
        from . import events  # noqa: F401
```

For more information about GitHub webhook events and payloads, see these pages in the GitHub docs:

- [Webhook events and payloads](https://docs.github.com/en/webhooks/webhook-events-and-payloads)
- [About webhooks](https://docs.github.com/en/webhooks/about-webhooks)

For more details about how `gidgethub.sansio.Event` and webhook routing work, see the [gidgethub documentation](https://gidgethub.readthedocs.io).

### Mentions

django-github-app provides a `@gh.mention` decorator to easily respond when your GitHub App is mentioned in comments. This is useful for building interactive bots that respond to user commands.

For ASGI projects:

```python
# your_app/events.py
import re
from django_github_app.routing import GitHubRouter
from django_github_app.mentions import MentionScope

gh = GitHubRouter()

# Respond to mentions of your bot
@gh.mention(username="mybot")
async def handle_bot_mention(event, gh, *args, context, **kwargs):
    """Respond when someone mentions @mybot"""
    mention = context.mention
    issue_url = event.data["issue"]["comments_url"]

    await gh.post(
        issue_url,
        data={"body": f"Hello! You mentioned me at position {mention.position}"},
    )


# Use regex to match multiple bot names
@gh.mention(username=re.compile(r".*-bot"))
async def handle_any_bot(event, gh, *args, context, **kwargs):
    """Respond to any mention ending with '-bot'"""
    mention = context.mention
    await gh.post(
        event.data["issue"]["comments_url"],
        data={"body": f"Bot {mention.username} at your service!"},
    )


# Restrict to pull request mentions only
@gh.mention(username="deploy-bot", scope=MentionScope.PR)
async def handle_deploy_command(event, gh, *args, context, **kwargs):
    """Only respond to @deploy-bot in pull requests"""
    await gh.post(
        event.data["issue"]["comments_url"], data={"body": "Starting deployment..."}
    )
```

For WSGI projects:

```python
# your_app/events.py
import re
from django_github_app.routing import GitHubRouter
from django_github_app.mentions import MentionScope

gh = GitHubRouter()

# Respond to mentions of your bot
@gh.mention(username="mybot")
def handle_bot_mention(event, gh, *args, context, **kwargs):
    """Respond when someone mentions @mybot"""
    mention = context.mention
    issue_url = event.data["issue"]["comments_url"]

    gh.post(
        issue_url,
        data={"body": f"Hello! You mentioned me at position {mention.position}"},
    )
```

The mention decorator automatically extracts mentions from comments and provides context about each mention. Handlers are called once for each matching mention in a comment.

## Features

### GitHub API Client

The library provides `AsyncGitHubAPI` and `SyncGitHubAPI`, implementations of gidgethub's abstract `GitHubAPI` class that handle authentication and use [httpx](https://github.com/encode/httpx) as their HTTP client. While they're automatically provided in webhook handlers, you can also use them directly in your code.

The clients automatically handle authentication and token refresh when an installation ID is provided. The installation ID is GitHub's identifier for where your app is installed, which you can get from the `installation_id` field on the `Installation` model.

#### `AsyncGitHubAPI`

For Django projects running with ASGI or in async views, the async client provides the most efficient way to interact with GitHub's API. It's particularly useful when making multiple API calls or in webhook handlers that need to respond quickly.

```python
from django_github_app.github import AsyncGitHubAPI
from django_github_app.models import Installation


# Access public endpoints without authentication
async def get_public_repo():
    async with AsyncGitHubAPI("example-github-app") as gh:
        return await gh.getitem("/repos/django/django")


# Interact as the GitHub App installation
async def create_comment(repo_full_name: str):
    # Get the installation for the repository
    installation = await Installation.objects.aget(
        repositories__full_name=repo_full_name
    )

    async with AsyncGitHubAPI(
        "example-github-app", installation_id=installation.installation_id
    ) as gh:
        await gh.post(
            f"/repos/{repo_full_name}/issues/1/comments", data={"body": "Hello!"}
        )

    # You can either provide the `installation_id` as above, or the `Installation` instance
    # itself
    async with AsyncGitHubAPI("example-github-app", installation=installation) as gh:
        await gh.post(
            f"/repos/{repo_full_name}/issues/1/comments", data={"body": "World!"}
        )
```

#### `SyncGitHubAPI`

For traditional Django applications running under WSGI, the sync client provides a straightforward way to interact with GitHub's API without dealing with `async`/`await`.

```python
from django_github_app.github import SyncGitHubAPI
from django_github_app.models import Installation


# Access public endpoints without authentication
def get_public_repo_sync():
    with SyncGitHubAPI("example-github-app") as gh:
        return gh.getitem("/repos/django/django")


# Interact as the GitHub App installation
def create_comment_sync(repo_full_name: str):
    # Get the installation for the repository
    installation = Installation.objects.get(repositories__full_name=repo_full_name)

    with SyncGitHubAPI(
        "example-github-app", installation_id=installation.installation_id
    ) as gh:
        gh.post(f"/repos/{repo_full_name}/issues/1/comments", data={"body": "Hello!"})

    # You can either provide the `installation_id` as above, or the `Installation` instance
    # itself
    with SyncGitHubAPI("example-github-app", installation=installation) as gh:
        gh.post(f"/repos/{repo_full_name}/issues/1/comments", data={"body": "World!"})
```

### Models

django-github-app provides models that handle the persistence and retrieval of GitHub App data. These models abstract away common patterns when working with GitHub Apps: storing webhook events, managing installation authentication, and tracking repository access.

All models and their managers provide async methods for database operations and GitHub API interactions, with sync wrappers where appropriate.

#### `EventLog`

`django_github_app.models.EventLog` maintains a history of incoming webhook events, storing both the event type and its full payload.

It also has support for automatically cleaning up old events based on your configuration, via the `acleanup_events` manager method and the `GITHUB_APP["DAYS_TO_KEEP_EVENTS"]` setting. For more details, see the sections on [`AUTO_CLEANUP_EVENTS`](#auto_cleanup_events) and [`DAYS_TO_KEEP_EVENTS`](#days_to_keep_events) in the [Configuration](#configuration) documentation below.

The model primarily serves the webhook handling system, but you can also use it to query past events if needed.

##### Manager methods

- `acreate_from_event`/`create_from_event`: Store incoming webhook events _(primarily for internal use)_
- `acleanup_events`/`cleanup_events`: Remove events older than specified days

##### Properties

- `action`: Extract action from event payload, if present

#### `Installation`

`django_github_app.models.Installation` represents where your GitHub App is installed. It stores the installation ID and metadata from GitHub, and provides methods for authentication.

```python
from django_github_app.github import AsyncGitHubAPI
from django_github_app.models import Installation

# Get an installation and its access token
installation = await Installation.objects.aget(repositories__full_name="owner/repo")
async with AsyncGitHubAPI(installation_id=installation.installation_id) as gh:
    # Authenticated as this installation
    await gh.post("/repos/owner/repo/issues", data={"title": "Hello!"})
```

##### Manager methods

- `acreate_from_event`/`create_from_event`: Create from installation events _(primarily for internal use)_
- `acreate_from_gh_data`/`create_from_gh_data`: Create from GitHub API response data _(primarily for internal use)_
- `aget_from_event`/`get_from_event`: Retrieve installation from webhook events (`gidgethub.sansio.Event`)

##### Model methods

- `get_gh_client`: Get configured API client for this installation
- `aget_access_token`/`get_access_token`: Generate GitHub access token for API calls
- `arefresh_from_gh`/`refresh_from_gh`: Update an installation's data from GitHub
- `aget_repos`/`get_repos`: Fetch installation's accessible repositories

#### `Repository`

`django_github_app.models.Repository` tracks repositories where your app is installed and provides high-level methods for GitHub operations.

```python
from django_github_app.models import Repository

# Get open issues for a repository
repo = await Repository.objects.aget(full_name="owner/repo")
issues = await repo.aget_issues(params={"state": "open"})
```

##### Manager methods

- `acreate_from_gh_data`/`create_from_gh_data`: Create from GitHub API response data _(primarily for internal use)_
- `aget_from_event`/`get_from_event`: Retrieve repository from webhook events (`gidgethub.sansio.Event`)

##### Model methods

- `get_gh_client`: Get configured API client for this repository
- `aget_issues`/`get_issues`: Fetch repository's issues

##### Properties

- `owner`: Repository owner from full name
- `repo`: Repository name from full name

### Built-in Event Handlers

The library includes event handlers for managing GitHub App installations and repositories. These handlers automatically update your `Installation` and `Repository` models in response to GitHub webhooks:

- Installation events:
  - `installation.created`: Creates new `Installation` record
  - `installation.deleted`: Removes `Installation` record
  - `installation.suspend`/`installation.unsuspend`: Updates `Installation` status
  - `installation.new_permissions_accepted`: Updates `Installation` data
  - `installation_repositories`: Creates and/or removes the `Repository` models associated with `Installation`

- Repository events:
  - `repository.renamed`: Updates repository details

The library loads either async or sync versions of these handlers based on your `GITHUB_APP["WEBHOOK_TYPE"]` setting.

### Mentions

The `@gh.mention` decorator provides a powerful way to build interactive GitHub Apps that respond to mentions in comments. When users mention your app (e.g., `@mybot help`), the decorator automatically detects these mentions and routes them to your handlers.

The mention system:
1. Monitors incoming webhook events for comments containing mentions
2. Extracts all mentions while ignoring those in code blocks, inline code, or blockquotes
3. Filters mentions based on your specified criteria (username pattern, scope)
4. Calls your handler once for each matching mention, providing rich context

#### Context

Each handler receives a `context` parameter with detailed information about the mention:

```python
@gh.mention(username="mybot")
async def handle_mention(event, gh, *args, context, **kwargs):
    mention = context.mention

    # Access mention details
    print(f"Username: {mention.username}")  # "mybot"
    print(f"Position: {mention.position}")  # Character position in comment
    print(f"Line: {mention.line_info.lineno}")  # Line number (1-based)
    print(f"Line text: {mention.line_info.text}")  # Full text of the line

    # Navigate between mentions in the same comment
    if mention.previous_mention:
        print(f"Previous: @{mention.previous_mention.username}")
    if mention.next_mention:
        print(f"Next: @{mention.next_mention.username}")

    # Check the scope (ISSUE, PR, or COMMIT)
    print(f"Scope: {context.scope}")
```

#### Filtering Options

##### Username Patterns

Filter mentions by username using exact matches or regular expressions:

```python
# Exact match (case-insensitive)
@gh.mention(username="deploy-bot")
def exact_match_mention():
    ...


# Regular expression pattern
@gh.mention(username=re.compile(r".*-bot"))
def regex_mention():
    ...


# Respond to all mentions (no filter)
@gh.mention()
def all_mentions():
    ...
```

##### Scopes

Limit mentions to specific GitHub contexts:

```python
from django_github_app.mentions import MentionScope

# Only respond in issues (not PRs)
@gh.mention(username="issue-bot", scope=MentionScope.ISSUE)
def issue_mention():
    ...


# Only respond in pull requests
@gh.mention(username="review-bot", scope=MentionScope.PR)
def pull_request_mention():
    ...


# Only respond in commit comments
@gh.mention(username="commit-bot", scope=MentionScope.COMMIT)
def commit_mention():
    ...
```

Scope mappings:
- `MentionScope.ISSUE`: Issue comments only
- `MentionScope.PR`: PR comments, PR reviews, and PR review comments
- `MentionScope.COMMIT`: Commit comments only

#### Parsing Rules

The mention parser follows GitHub's rules:

- **Valid mentions**: Must start with `@` followed by a GitHub username
- **Username format**: 1-39 characters, alphanumeric or single hyphens, no consecutive hyphens
- **Position**: Must be preceded by whitespace or start of line
- **Exclusions**: Mentions in code blocks, inline code, or blockquotes are ignored

Examples:
```
@bot help                    ✓ Detected
Hey @bot can you help?       ✓ Detected
@deploy-bot start            ✓ Detected
See @user's comment          ✓ Detected

email@example.com            ✗ Not a mention
@@bot                        ✗ Invalid format
`@bot help`                  ✗ Inside code
```@bot in code```           ✗ Inside code block
> @bot quoted                ✗ Inside blockquote
```

#### Multiple Mentions

When a comment contains multiple mentions, each matching mention triggers a separate handler call:

```python
@gh.mention(username=re.compile(r".*-bot"))
async def handle_bot_mention(event, gh, *args, context, **kwargs):
    mention = context.mention

    # For comment: "@deploy-bot start @test-bot validate @user check"
    # This handler is called twice:
    # 1. For @deploy-bot (mention.username = "deploy-bot")
    # 2. For @test-bot (mention.username = "test-bot")
    # The @user mention is filtered out by the regex pattern
```

### System Checks

The library includes Django system checks to validate your webhook configuration:

#### `django_github_app.E001`

Error raised when both `AsyncWebhookView` and `SyncWebhookView` are detected in your URL configuration. You must use either async or sync webhooks consistently throughout your project, not both.

To fix this error, ensure all your webhook views are of the same type:

- Use `AsyncWebhookView` for all webhook endpoints in ASGI projects
- Use `SyncWebhookView` for all webhook endpoints in WSGI projects

## Configuration

Configuration of django-github-app is done through a `GITHUB_APP` dictionary in your Django project's `DJANGO_SETTINGS_MODULE`.

Here is an example configuration with the default values shown:

```python
GITHUB_APP = {
    "APP_ID": "",
    "AUTO_CLEANUP_EVENTS": True,
    "CLIENT_ID": "",
    "DAYS_TO_KEEP_EVENTS": 7,
    "LOG_ALL_EVENTS": True,
    "NAME": "",
    "PRIVATE_KEY": "",
    "WEBHOOK_SECRET": "",
    "WEBHOOK_TYPE": "async",
}
```

The following settings are required:

- `APP_ID`
- `CLIENT_ID`
- `NAME`
- `PRIVATE_KEY`
- `WEBHOOK_SECRET`
- `WEBHOOK_TYPE`

### `APP_ID`

> 🔴 **Required** | `str`

The GitHub App's unique identifier. Obtained when registering your GitHub App.

### `AUTO_CLEANUP_EVENTS`

> **Optional** | `bool` | Default: `True`

Boolean flag to enable automatic cleanup of old webhook events. If enabled, `EventLog` instances older than [`DAYS_TO_KEEP_EVENTS`](#days_to_keep_events) (default: 7 days) are deleted during webhook processing.

Set to `False` to either retain events indefinitely or manage cleanup separately using `EventLog.objects.acleanup_events` with a task runner like [Django-Q2](https://github.com/django-q2/django-q2) or [Celery](https://github.com/celery/celery).

### `CLIENT_ID`

> 🔴 **Required** | `str`

The GitHub App's client ID. Obtained when registering your GitHub App.

### `DAYS_TO_KEEP_EVENTS`

> **Optional** | `int` | Default: `7`

Number of days to retain webhook events before cleanup. Used by both automatic cleanup (when [`AUTO_CLEANUP_EVENTS`](#auto_cleanup_events) is `True`) and the `EventLog.objects.acleanup_events` manager method.

### `LOG_ALL_EVENTS`

> **Optional** | `bool` | Default: `True`

Controls whether all webhook events are stored in the database, or only events that have registered handlers.

When `True` (default), all webhook events sent to your webhook endpoint are stored as `EventLog` entries, providing a complete audit trail. This is useful for debugging and compliance purposes.

When `False`, only events that have registered handlers (via `@router.event()` decorators) are stored. This can significantly reduce database usage for high-traffic GitHub Apps, especially those receiving many events they don't process (e.g., the numerous pull request sub-events like "labeled", "unlabeled", etc.).

Example:
```python
GITHUB_APP = {
    # ... other settings ...
    "LOG_ALL_EVENTS": False,  # Only store events with handlers
}
```

### `NAME`

> 🔴 **Required** | `str`

The GitHub App's name as registered on GitHub.

### `PRIVATE_KEY`

> 🔴 **Required** | `str`

The GitHub App's private key for authentication. Can be provided as either:

- Raw key contents (e.g., from an environment variable)
- Path to key file (as a `str` or `Path` object)

The library will automatically detect and read the key file if a path is provided.

```python
from pathlib import Path

from environs import Env

env = Env()

# Key contents from environment
GITHUB_APP = {
    "PRIVATE_KEY": env.str("GITHUB_PRIVATE_KEY"),
}

# Path to local key file (as string)
GITHUB_APP = {
    "PRIVATE_KEY": "/path/to/private-key.pem",
}

# Path to local key file (as Path object)
GITHUB_APP = {
    "PRIVATE_KEY": Path("path/to/private-key.pem"),
}

# Path from environment
GITHUB_APP = {
    "PRIVATE_KEY": env.path("GITHUB_PRIVATE_KEY_PATH"),
}
```

> [!NOTE]
> The private key should be kept secure and never committed to version control. Using environment variables or secure file storage is recommended.

### `WEBHOOK_SECRET`

> 🔴 **Required** | `str`

Secret used to verify webhook payloads from GitHub.

### `WEBHOOK_TYPE`

> 🔴 **Required** | `Literal["async", "sync"]` | Default: `"async"`

Determines whether the library uses async or sync handlers for processing webhook events:

- `"async"`: Use with `AsyncWebhookView` in ASGI projects
- `"sync"`: Use with `SyncWebhookView` in WSGI projects

## Development

For detailed instructions on setting up a development environment and contributing to this project, see [CONTRIBUTING.md](CONTRIBUTING.md).

For release procedures, see [RELEASING.md](RELEASING.md).

## License

django-github-app is licensed under the MIT license. See the [`LICENSE`](LICENSE) file for more information.
