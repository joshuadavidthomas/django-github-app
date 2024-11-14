<!-- docs-intro-begin -->
# django-github-app

[![PyPI](https://img.shields.io/pypi/v/django-github-app)](https://pypi.org/project/django-github-app/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/django-github-app)
![Django Version](https://img.shields.io/badge/django-4.2%20%7C%205.0%20%7C%205.1-%2344B78B?labelColor=%23092E20)
<!-- https://shields.io/badges -->
<!-- django-4.2 | 5.0 | 5.1-#44B78B -->
<!-- labelColor=%23092E20 -->

<!-- docs-intro-end -->

## Requirements

- Python 3.10, 3.11, 3.12, 3.13
- Django 4.2, 5.0, 5.1

## Installation

1. Register a new GitHub App, following [these instructions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app) from the GitHub Docs. For a more detailed tutorial, there is also [this page](https://docs.github.com/en/apps/creating-github-apps/writing-code-for-a-github-app/building-a-github-app-that-responds-to-webhook-events) -- in particular the section on [Setup](https://docs.github.com/en/apps/creating-github-apps/writing-code-for-a-github-app/building-a-github-app-that-responds-to-webhook-events#setup).

   Make note of the following information while setting up your new GitHub App:

    - App ID
    - Client ID
    - Name
    - Private Key
    - Webhook Secret
    - Webhook URL

   For the Private Key, you will be able to use either the file contents or the file itself to authenticate with GitHub. See step 5 below for more information about private key configuration.

   For the Webhook URL, the endpoint is up to you. See step 4 below for how the endpoint is configured. Using these installation instructions as an example, you would enter `<your project's base url>/gh/` as the Webhook URL.

2. Install the package from PyPI:

    ```bash
    python -m pip install django-github-app

    # or if you like the new hotness

    uv add django-github-app
    uv sync
    ```

3. Add the app to your Django project's `INSTALLED_APPS`:

    ```python
    INSTALLED_APPS = [
        "django_github_app",
    ]
    ```

4. Add django-github-app's webhook view to your Django project's urls:

   ```python
   from django.urls import path
   
   from django_github_app.views import AsyncWebhookView
   
   urlpatterns = [
       path("gh/", AsyncWebhookView.as_view()),
   ]
   ```

   For the moment, django-github-app only supports an async webhook view, as this library is a wrapper around [gidgethub](https://github.com/gidgethub/gidgethub) which is async only. Sync support is planned.

   As noted above in step 1, the path here must match the Webhook URL you entered when setting up your GitHub App.

5. Add the following dictionary to your Django project's `DJANGO_SETTINGS_MODULE`, filling in the values from step 1 above. The example below uses [environs](https://github.com/sloria/environs) to load the values from an `.env` file.

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
    }
    ```

> [!NOTE]
> In this example, the private key's contents are set and loaded directly from the environment. If you prefer to use the file itself, you could do something like this instead:
>
> ```python
> from pathlib import Path
> 
> GITHUB_APP = {
>     "PRIVATE_KEY": Path(env.path("GITHUB_PRIVATE_KEY_PATH")).read_text(),
> }
> ```

## Getting Started

django-github-app provides a router-based system for handling GitHub webhook events, built on top of [gidgethub](https://github.com/gidgethub/gidgethub). The router matches incoming webhooks to your handler functions based on the event type and optional action.

Each handler receives two key arguments:

- `event`: A `gidgethub.sansio.Event` containing the webhook payload
- `gh`: A `gidgethub.abc.GitHubAPI` instance for making API calls
  
<add note about `django_github_app.github.AsyncGitHubAPI` which is what actually is passed as `gh`. it's an opinionated implementation of the abstract GitHubAPI provided by gidgethub and uses httpx as it's client>

Here's an example:

```python
from django_github_app.routing import Router

gh = Router()

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
        await gh.post(
            issue["labels_url"], 
            data=labels
        )

# Handle specific issue actions
@gh.event("issues", action="opened")
async def welcome_new_issue(event, gh, *args, **kwargs):
    """Post a comment when a new issue is opened"""
    url = event.data["issue"]["comments_url"]
    await gh.post(url, data={
        "body": "Thanks for opening an issue! We'll take a look soon."
    })
```

In this example, we automatically label issues based on their title and post a welcome comment on newly opened issues. The router ensures each webhook is directed to the appropriate handler based on the event type and action.

> [!NOTE]
> Handlers must be async functions as django-github-app uses gidgethub for webhook event routing which only supports async operations. Sync support is planned to better integrate with Django projects that don't use async.

For more information about GitHub webhook events and payloads, see:

- [Webhook events and payloads](https://docs.github.com/en/webhooks/webhook-events-and-payloads)
- [About webhooks](https://docs.github.com/en/webhooks/about-webhooks)

## Features

### GitHub API Client

The library provides `AsyncGitHubAPI`, an implementation of gidgethub's abstract `GitHubAPI` class that handles authentication and uses [httpx](https://github.com/encode/httpx) as its HTTP client. While it's automatically provided in webhook handlers, you can also use it directly in your code:

```python
from django_github_app.github import AsyncGitHubAPI
from django_github_app.models import Installation

# Access public endpoints without authentication
async def get_public_repo():
    async with AsyncGitHubAPI() as gh:
        return await gh.getitem("/repos/django/django")

# Interact as the GitHub App installation
async def create_comment(repo_full_name: str):
    # Get the installation for the repository
    installation = await Installation.objects.aget(repositories__full_name=repo_full_name)
    
    async with AsyncGitHubAPI(installation_id=installation.installation_id) as gh:
        await gh.post(
            f"/repos/{repo_full_name}/issues/1/comments",
            data={"body": "Hello!"}
        )
```

The client automatically handles authentication and token refresh when an installation ID is provided. The installation ID is GitHub's identifier for where your app is installed, which you can get from the `installation_id` field on the `Installation` model.

### Models

#### `EventLog`

Stores incoming webhook events with their payload and timestamp. Includes automatic cleanup of old events based on the `DAYS_TO_KEEP_EVENTS` setting via a `EventLog.objects.acleanup_events` manager method.

#### `Installation`

Represents where your GitHub App is installed. Stores the installation ID and metadata from GitHub, and provides methods for authentication:

```python
from django_github_app.models import Installation

# Get an installation and its access token
installation = await Installation.objects.aget(repositories__full_name="owner/repo")
async with AsyncGitHubAPI(installation_id=installation.installation_id) as gh:
    # Do something as the installation
```

#### `Repository`

Represents repositories where your app is installed. Provides convenience methods for common GitHub operations:

```python
from django_github_app.models import Repository

# Get issues for a repository
repo = await Repository.objects.aget(full_name="owner/repo")
issues = await repo.aget_issues()
```

All models provide both async and sync versions of their methods, though async is recommended for better performance.

## Configuration

Configuration of django-github-app is done through a `GITHUB_APP` dictionary in your Django project's `DJANGO_SETTINGS_MODULE`.

Here is an example configuration with the default values shown:

```python
GITHUB_APP = {
    "APP_ID": "",
    "AUTO_CLEANUP_EVENTS": True,
    "CLIENT_ID": "",
    "DAYS_TO_KEEP_EVENTS": 7,
    "NAME": "",
    "PRIVATE_KEY": "",
    "WEBHOOK_SECRET": "",
}
```

The following settings are required:

- `APP_ID`
- `CLIENT_ID`
- `NAME`
- `PRIVATE_KEY`
- `WEBHOOK_SECRET`

### `APP_ID`

> ❗ **Required** | `str`

The GitHub App's unique identifier. Obtained when registering your GitHub App.

### `AUTO_CLEANUP_EVENTS`

> **Optional** | `bool` | Default: `True`

Boolean flag to enable automatic cleanup of old webhook events.

### `CLIENT_ID`

> ❗ **Required** | `str`

The GitHub App's client ID. Obtained when registering your GitHub App.

### `DAYS_TO_KEEP_EVENTS`

> **Optional** | `int` | Default: `7`

Number of days to retain webhook events before cleanup.

### `NAME`

> ❗ **Required** | `str`

The GitHub App's name as registered on GitHub.

### `PRIVATE_KEY`

> ❗ **Required** | `str`

The GitHub App's private key for authentication. Can be provided as:

- Raw key contents in environment variable
- File contents read from disk: `Path("path/to/key.pem").read_text()`

### `WEBHOOK_SECRET`

> **Required** | `str`

Secret used to verify webhook payloads from GitHub.

## License

django-github-app is licensed under the MIT license. See the [`LICENSE`](LICENSE) file for more information.
