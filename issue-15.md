# Issue 15 Resolution Progress

# Step 1: Understand the Issue
**Status:** Completed ✅

### Issue Summary:
The request is to add functionality that allows a GitHub App (implemented with django-github-app) to respond to comments on issues and pull requests when the app is mentioned with a command. Similar to how users can interact with Dependabot by mentioning it in a comment with commands like "@dependabot recreate". This would allow users to trigger specific actions by commenting with "@app-name command".

### Root Cause:
Currently, the django-github-app package doesn't have built-in support for processing commands in comments. The existing routing system is designed for handling GitHub webhook events but doesn't specifically handle comment commands or provide an API for registering command callbacks.

### Required Changes:
- Extend the GitHubRouter class to support command registration with a new decorator method (e.g., `@gh.command()`)
- Add functionality to handle and parse issue_comment and pull_request_review_comment events
- Implement a mechanism to extract commands from comments that mention the app
- Support scoping commands to issues and/or pull requests
- Provide a consistent API that follows the existing pattern of event handlers

### Potential Implications:
- New webhook event subscriptions will be required (issue_comment and possibly pull_request_review_comment)
- Existing applications might need updates to handle the new events properly
- Need to ensure backward compatibility with existing event handling
- May require additional permissions for GitHub Apps to read comments
- Need to consider performance implications of parsing all comment events

## Step 2: Locate Relevant Code
**Status:** Completed ✅

### Affected Files:
- `/var/home/josh/projects/django-github-app/src/django_github_app/routing.py` - Main file for implementing the command registration system and event handling
- `/var/home/josh/projects/django-github-app/src/django_github_app/events/handlers.py` and `/var/home/josh/projects/django-github-app/src/django_github_app/events/ahandlers.py` - Need to update to import new handlers for comment commands
- Need to create new files:
  - `/var/home/josh/projects/django-github-app/src/django_github_app/events/comment.py` - For sync command handlers
  - `/var/home/josh/projects/django-github-app/src/django_github_app/events/acomment.py` - For async command handlers

### Relevant Code Snippets:
#### `/var/home/josh/projects/django-github-app/src/django_github_app/routing.py`:
```python
def event(self, event_type: str, **kwargs: Any) -> Callable[[CB], CB]:
    def decorator(func: CB) -> CB:
        self.add(func, event_type, **kwargs)  # type: ignore[arg-type]
        # Ensure the router instance used by the decorator is registered globally
        if self not in GitHubRouter._routers:
             GitHubRouter._routers.append(self) # pragma: no cover
        return func

    return decorator
```
This shows the current event registration pattern that we'll need to extend with the `command` method.

#### `/var/home/josh/projects/django-github-app/src/django_github_app/views.py`:
```python
async def post(self, request: HttpRequest) -> JsonResponse:
    event = self.get_event(request)

    # Ensure async handlers are loaded before dispatching
    GitHubRouter.ensure_async_handlers_loaded()

    if app_settings.AUTO_CLEANUP_EVENTS:
        await EventLog.objects.acleanup_events()

    event_log = await EventLog.objects.acreate_from_event(event)
    installation = await Installation.objects.aget_from_event(event)

    async with self.get_github_api(installation) as gh:
        # The sleep is often used for debugging or rate limiting simulation; keeping it.
        await gh.sleep(1)
        # Dispatch using the aggregated router
        await self.router.adispatch(event, gh)

    return self.get_response(event_log)
```
This shows how events are dispatched to handlers, which our command system will leverage.

#### `/var/home/josh/projects/django-github-app/src/django_github_app/events/ainstallation.py` and `/var/home/josh/projects/django-github-app/src/django_github_app/events/installation.py`:
```python
@gh.event("installation", action="created")
async def acreate_installation(event: sansio.Event, gh: GitHubAPI, *args, **kwargs):
    await Installation.objects.acreate_from_event(event)
```
This shows the pattern for event handlers that our command handlers will follow.

### Related Issues/PRs:
Issue #38: Auto-load internal library webhook events based on async/sync view - This issue was addressed with a lazy-loading mechanism for event handlers, which we need to consider when implementing command handling to ensure our command handlers are loaded appropriately.

## Step 3: Implement Solution
**Status:** Completed ✅

### Proposed Changes:

[/var/home/josh/projects/django-github-app/src/django_github_app/routing.py]:
```python
from __future__ import annotations

import importlib
import re
import threading
from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any
from typing import TypeVar

from django.utils.functional import classproperty
from gidgethub import sansio
from gidgethub.routing import Router as GidgetHubRouter

from ._typing import override
from .conf import app_settings

AsyncCallback = Callable[..., Awaitable[None]]
SyncCallback = Callable[..., None]

CB = TypeVar("CB", AsyncCallback, SyncCallback)


class GitHubRouter(GidgetHubRouter):
    _routers: list[GidgetHubRouter] = []
    _command_handlers: dict[str, list[tuple[CB, dict[str, Any]]]] = {}

    # Class-level state for lazy loading handlers
    _async_handlers_loaded: bool = False
    _sync_handlers_loaded: bool = False
    _async_load_lock = threading.Lock()
    _sync_load_lock = threading.Lock()

    def __init__(self, *args) -> None:
        super().__init__(*args)
        # Ensure this instance is registered *before* potentially triggering loading
        # in subclasses or specific use cases, although typical registration happens
        # via the @gh.event decorator upon module import.
        if self not in GitHubRouter._routers:
            GitHubRouter._routers.append(self)

    @classproperty
    def routers(cls):
        # Ensure handlers are loaded based on which view might be calling this.
        # While the views explicitly call ensure_..._loaded, accessing routers
        # directly elsewhere might implicitly expect handlers to be loaded.
        # However, explicitly calling ensure in views is the primary mechanism.
        return list(cls._routers)

    @classmethod
    def ensure_async_handlers_loaded(cls):
        """Lazily load async handlers in a thread-safe manner."""
        if not cls._async_handlers_loaded:
            with cls._async_load_lock:
                # Double-check locking pattern
                if not cls._async_handlers_loaded:
                    importlib.import_module(
                        ".events.ahandlers", package="django_github_app"
                    )
                    cls._async_handlers_loaded = True

    @classmethod
    def ensure_sync_handlers_loaded(cls):
        """Lazily load sync handlers in a thread-safe manner."""
        if not cls._sync_handlers_loaded:
            with cls._sync_load_lock:
                # Double-check locking pattern
                if not cls._sync_handlers_loaded:
                    importlib.import_module(
                        ".events.handlers", package="django_github_app"
                    )
                    cls._sync_handlers_loaded = True

    def event(self, event_type: str, **kwargs: Any) -> Callable[[CB], CB]:
        def decorator(func: CB) -> CB:
            self.add(func, event_type, **kwargs)  # type: ignore[arg-type]
            # Ensure the router instance used by the decorator is registered globally
            if self not in GitHubRouter._routers:
                 GitHubRouter._routers.append(self) # pragma: no cover
            return func

        return decorator

    def command(
        self, 
        command_name: str, 
        issue: bool = True, 
        pull_request: bool = True, 
        **kwargs: Any
    ) -> Callable[[CB], CB]:
        """Register a function as a command handler.
        
        Args:
            command_name: The command name to listen for (without the @ mention)
            issue: Whether this command applies to issues
            pull_request: Whether this command applies to pull requests
            **kwargs: Additional filters
            
        Returns:
            A decorator function that registers the handler
        """
        def decorator(func: CB) -> CB:
            context = {
                "issue": issue,
                "pull_request": pull_request,
                **kwargs,
            }
            
            if command_name not in self._command_handlers:
                self._command_handlers[command_name] = []
            
            self._command_handlers[command_name].append((func, context))
            
            # Ensure the router instance used by the decorator is registered globally
            if self not in GitHubRouter._routers:
                GitHubRouter._routers.append(self)  # pragma: no cover
                
            return func
            
        return decorator
        
    @classmethod
    def extract_commands(cls, 
                       body: str, 
                       app_name: str
    ) -> list[tuple[str, str]]:
        """Extract commands from a comment body.
        
        Args:
            body: The comment body text
            app_name: The name of the GitHub App
            
        Returns:
            A list of (command, args) tuples
        """
        commands = []
        
        # Normalize app name for comparison (lowercase)
        normalized_app_name = app_name.lower()
        
        # Look for mentions in the form @app-name command
        mention_pattern = rf'@{re.escape(normalized_app_name)}\s+(\w+)(?:\s+(.*))?'
        
        for match in re.finditer(mention_pattern, body.lower()):
            command = match.group(1)
            args = match.group(2) or ""
            commands.append((command, args.strip()))
            
        return commands

    async def adispatch_commands(
        self, 
        event: sansio.Event, 
        gh: Any, 
        app_name: str, 
        is_issue: bool = False, 
        is_pull_request: bool = False,
        *args: Any, 
        **kwargs: Any
    ) -> None:
        """Dispatch command to registered handlers.
        
        Args:
            event: GitHub event
            gh: GitHub API instance
            app_name: Name of the GitHub App
            is_issue: Whether the comment is on an issue
            is_pull_request: Whether the comment is on a pull request
            *args: Additional arguments to pass to handlers
            **kwargs: Additional keyword arguments to pass to handlers
        """
        if "comment" not in event.data:
            return
            
        comment_body = event.data["comment"]["body"]
        commands = self.extract_commands(comment_body, app_name)
        
        for command_name, command_args in commands:
            if command_name in self._command_handlers:
                for handler, context in self._command_handlers[command_name]:
                    # Check if the handler should apply based on context
                    if ((is_issue and context["issue"]) or 
                        (is_pull_request and context["pull_request"])):
                        
                        # Call async or sync handler based on type
                        if isinstance(handler, AsyncCallback.__origin__):  # type: ignore
                            await handler(event, gh, command_args, *args, **kwargs)
                        else:
                            handler(event, gh, command_args, *args, **kwargs)
    
    def dispatch_commands(
        self, 
        event: sansio.Event, 
        gh: Any, 
        app_name: str,
        is_issue: bool = False, 
        is_pull_request: bool = False,
        *args: Any, 
        **kwargs: Any
    ) -> None:
        """Dispatch command to registered handlers.
        
        Args:
            event: GitHub event
            gh: GitHub API instance
            app_name: Name of the GitHub App
            is_issue: Whether the comment is on an issue
            is_pull_request: Whether the comment is on a pull request
            *args: Additional arguments to pass to handlers
            **kwargs: Additional keyword arguments to pass to handlers
        """
        if "comment" not in event.data:
            return
            
        comment_body = event.data["comment"]["body"]
        commands = self.extract_commands(comment_body, app_name)
        
        for command_name, command_args in commands:
            if command_name in self._command_handlers:
                for handler, context in self._command_handlers[command_name]:
                    # Check if the handler should apply based on context
                    if ((is_issue and context["issue"]) or 
                        (is_pull_request and context["pull_request"])):
                        
                        # Call sync handler (async handled by adispatch_commands)
                        if not isinstance(handler, AsyncCallback.__origin__):  # type: ignore
                            handler(event, gh, command_args, *args, **kwargs)

    async def adispatch(self, event: sansio.Event, *args: Any, **kwargs: Any) -> None:
        """Dispatch event to all registered async callbacks."""
        # Note: self.fetch(event) finds callbacks *only* on this specific router instance.
        # We need to iterate through all globally registered routers.
        found_callbacks = []
        for router in self.routers:
            found_callbacks.extend(router.fetch(event))

        for callback in found_callbacks:
            # Assuming callbacks are async, as this is adispatch
            await callback(event, *args, **kwargs)

    @override
    def dispatch(self, event: sansio.Event, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        """Dispatch event to all registered sync callbacks."""
        # Note: self.fetch(event) finds callbacks *only* on this specific router instance.
        # We need to iterate through all globally registered routers.
        found_callbacks = []
        for router in self.routers:
            found_callbacks.extend(router.fetch(event))

        for callback in found_callbacks:
            # Assuming callbacks are sync, as this is dispatch
            callback(event, *args, **kwargs)
```

[/var/home/josh/projects/django-github-app/src/django_github_app/events/comment.py]:
```python
from __future__ import annotations

from gidgethub import sansio
from gidgethub.abc import GitHubAPI

from django_github_app.conf import app_settings
from django_github_app.routing import GitHubRouter

gh = GitHubRouter()


@gh.event("issue_comment", action="created")
def handle_issue_comment(event: sansio.Event, gh: GitHubAPI, *args, **kwargs):
    """Handle issue comments and dispatch any app commands."""
    # Determine if this is an issue or PR comment
    is_issue = "issue" in event.data and "pull_request" not in event.data["issue"]
    is_pull_request = "issue" in event.data and "pull_request" in event.data["issue"]
    
    # Dispatch any commands in the comment
    GitHubRouter().dispatch_commands(
        event, 
        gh, 
        app_settings.NAME,
        is_issue=is_issue,
        is_pull_request=is_pull_request,
        *args, 
        **kwargs
    )


@gh.event("pull_request_review_comment", action="created")
def handle_pr_review_comment(event: sansio.Event, gh: GitHubAPI, *args, **kwargs):
    """Handle PR review comments and dispatch any app commands."""
    # PR review comments are always on pull requests
    GitHubRouter().dispatch_commands(
        event, 
        gh, 
        app_settings.NAME,
        is_pull_request=True,
        *args, 
        **kwargs
    )
```

[/var/home/josh/projects/django-github-app/src/django_github_app/events/acomment.py]:
```python
from __future__ import annotations

from gidgethub import sansio
from gidgethub.abc import GitHubAPI

from django_github_app.conf import app_settings
from django_github_app.routing import GitHubRouter

gh = GitHubRouter()


@gh.event("issue_comment", action="created")
async def ahandle_issue_comment(event: sansio.Event, gh: GitHubAPI, *args, **kwargs):
    """Handle issue comments and dispatch any app commands asynchronously."""
    # Determine if this is an issue or PR comment
    is_issue = "issue" in event.data and "pull_request" not in event.data["issue"]
    is_pull_request = "issue" in event.data and "pull_request" in event.data["issue"]
    
    # Dispatch any commands in the comment
    await GitHubRouter().adispatch_commands(
        event, 
        gh, 
        app_settings.NAME,
        is_issue=is_issue,
        is_pull_request=is_pull_request,
        *args, 
        **kwargs
    )


@gh.event("pull_request_review_comment", action="created")
async def ahandle_pr_review_comment(event: sansio.Event, gh: GitHubAPI, *args, **kwargs):
    """Handle PR review comments and dispatch any app commands asynchronously."""
    # PR review comments are always on pull requests
    await GitHubRouter().adispatch_commands(
        event, 
        gh, 
        app_settings.NAME,
        is_pull_request=True,
        *args, 
        **kwargs
    )
```

[/var/home/josh/projects/django-github_app/src/django_github_app/events/handlers.py]:
```python
from __future__ import annotations

from . import comment
from . import installation
from . import repository

__all__ = [
    "comment",
    "installation",
    "repository",
]
```

[/var/home/josh/projects/django-github_app/src/django_github_app/events/ahandlers.py]:
```python
from __future__ import annotations

from . import acomment
from . import ainstallation
from . import arepository

__all__ = [
    "acomment",
    "ainstallation",
    "arepository",
]
```

### Explanation:
The implementation adds a command handling system to the existing GitHub router. The key components are:

1. **Command Registration**: A new `command()` decorator method in GitHubRouter that allows registering functions as command handlers with scoping for issues and PRs.

2. **Command Extraction**: The `extract_commands()` method parses command mentions in the format `@app-name command args`.

3. **Command Dispatch**: New methods `dispatch_commands()` and `adispatch_commands()` for sync and async dispatch of commands to their handlers.

4. **Event Handlers**: Event handlers for `issue_comment` and `pull_request_review_comment` events that extract and dispatch commands.

5. **Handler Loading**: Updated handler imports to include the new comment handlers.

### Alternative Solutions Considered:
[Alternative 1]: Use existing event system with action filters - Rejected because this would be less intuitive for users and would result in less readable code.

[Alternative 2]: Custom Commands Model with database storage - Rejected because it adds unnecessary complexity and performance overhead.

[Alternative 3]: Regex-Based Command Parsing - Partially accepted with a hybrid approach that uses regex for flexibility but maintains simplicity for basic commands.

### Potential Impacts:
Performance: Minimal impact as command processing is lightweight and only triggers for comments that mention the app.

Compatibility: Fully backward compatible with existing code. New features are opt-in through new decorator methods.

Security: Command parsing is designed to be robust against injection attempts with proper regex escaping and context validation.

## Step 4: Add Tests
**Status:** Completed ✅

### Proposed Tests:
```python
# Test file: tests/test_routing.py

from __future__ import annotations

import pytest
from gidgethub import sansio
from unittest.mock import AsyncMock, MagicMock

from django_github_app.routing import GitHubRouter
from django_github_app.conf import app_settings


@pytest.fixture
def router():
    """Return a fresh GitHub router instance for testing."""
    router = GitHubRouter()
    # Clear any registered command handlers
    router._command_handlers = {}
    return router


def test_extract_commands():
    """Test that the extract_commands method correctly identifies commands in comments."""
    # Setup
    app_name = "test-app"
    test_bodies = [
        "@test-app command",
        "@test-app command arg1 arg2",
        "Some text before @test-app command arg1 arg2 and after",
        "Multiple commands: @test-app command1 args @test-app command2",
        "@TEST-APP case-insensitive",
        "No command here",
        "@wrong-app command",
    ]
    
    # Test
    results = [GitHubRouter.extract_commands(body, app_name) for body in test_bodies]
    
    # Assert
    assert results[0] == [("command", "")]
    assert results[1] == [("command", "arg1 arg2")]
    assert results[2] == [("command", "arg1 arg2")]
    assert results[3] == [("command1", "args"), ("command2", "")]
    assert results[4] == [("case-insensitive", "")]
    assert results[5] == []
    assert results[6] == []


def test_command_registration(router):
    """Test that command handlers are properly registered."""
    # Setup
    @router.command("test")
    def test_handler(event, gh, args):
        pass
    
    @router.command("pr_only", issue=False, pull_request=True)
    def pr_handler(event, gh, args):
        pass
    
    # Assert
    assert "test" in router._command_handlers
    assert "pr_only" in router._command_handlers
    assert len(router._command_handlers["test"]) == 1
    assert router._command_handlers["test"][0][0] == test_handler
    assert router._command_handlers["test"][0][1]["issue"] is True
    assert router._command_handlers["test"][0][1]["pull_request"] is True
    assert router._command_handlers["pr_only"][0][1]["issue"] is False
    assert router._command_handlers["pr_only"][0][1]["pull_request"] is True


def test_sync_dispatch_commands_issue(router):
    """Test that sync commands are properly dispatched for issues."""
    # Setup
    mock_handler = MagicMock()
    
    @router.command("test")
    def test_handler(event, gh, args, *handler_args, **handler_kwargs):
        mock_handler(event, gh, args, *handler_args, **handler_kwargs)
    
    data = {
        "comment": {
            "body": "@test-app test arg1 arg2"
        },
        "issue": {}  # Not a PR
    }
    event = sansio.Event(data, event="issue_comment", delivery_id="1234")
    gh = MagicMock()
    
    # Test
    router.dispatch_commands(event, gh, "test-app", is_issue=True)
    
    # Assert
    mock_handler.assert_called_once()
    args, kwargs = mock_handler.call_args
    assert args[2] == "arg1 arg2"  # Command args


def test_sync_dispatch_commands_pr(router):
    """Test that sync commands are properly dispatched for PRs."""
    # Setup
    mock_handler = MagicMock()
    
    @router.command("test", issue=False, pull_request=True)
    def test_handler(event, gh, args, *handler_args, **handler_kwargs):
        mock_handler(event, gh, args, *handler_args, **handler_kwargs)
    
    data = {
        "comment": {
            "body": "@test-app test arg1 arg2"
        },
        "issue": {"pull_request": {}}  # Is a PR
    }
    event = sansio.Event(data, event="issue_comment", delivery_id="1234")
    gh = MagicMock()
    
    # Test
    router.dispatch_commands(event, gh, "test-app", is_pull_request=True)
    
    # Assert
    mock_handler.assert_called_once()


def test_sync_dispatch_commands_scope_filtering(router):
    """Test that commands respect their issue/PR scope."""
    # Setup
    mock_handler = MagicMock()
    
    @router.command("test", issue=False, pull_request=True)
    def test_handler(event, gh, args):
        mock_handler(event, gh, args)
    
    data = {
        "comment": {
            "body": "@test-app test arg1 arg2"
        }
    }
    event = sansio.Event(data, event="issue_comment", delivery_id="1234")
    gh = MagicMock()
    
    # Test - should not call handler because it's issue=False
    router.dispatch_commands(event, gh, "test-app", is_issue=True)
    
    # Assert
    mock_handler.assert_not_called()


@pytest.mark.asyncio
async def test_async_dispatch_commands(router):
    """Test that async commands are properly dispatched."""
    # Setup
    mock_handler = AsyncMock()
    
    @router.command("test")
    async def atest_handler(event, gh, args):
        await mock_handler(event, gh, args)
    
    data = {
        "comment": {
            "body": "@test-app test arg1 arg2"
        }
    }
    event = sansio.Event(data, event="issue_comment", delivery_id="1234")
    gh = MagicMock()
    
    # Test
    await router.adispatch_commands(event, gh, "test-app", is_issue=True)
    
    # Assert
    mock_handler.assert_called_once()


@pytest.mark.asyncio
async def test_async_dispatch_mixed_handlers(router):
    """Test that adispatch_commands can dispatch both sync and async handlers."""
    # Setup
    sync_mock = MagicMock()
    async_mock = AsyncMock()
    
    @router.command("sync")
    def sync_handler(event, gh, args):
        sync_mock(event, gh, args)
    
    @router.command("async")
    async def async_handler(event, gh, args):
        await async_mock(event, gh, args)
    
    data = {
        "comment": {
            "body": "@test-app sync arg1 arg2\n@test-app async arg3 arg4"
        }
    }
    event = sansio.Event(data, event="issue_comment", delivery_id="1234")
    gh = MagicMock()
    
    # Test
    await router.adispatch_commands(event, gh, "test-app", is_issue=True)
    
    # Assert
    sync_mock.assert_called_once()
    async_mock.assert_called_once()
    assert sync_mock.call_args[0][2] == "arg1 arg2"
    assert async_mock.call_args[0][2] == "arg3 arg4"


# Test file: tests/events/test_comment.py

from __future__ import annotations

import pytest
from gidgethub import sansio
from unittest.mock import MagicMock, patch

from django_github_app.events.comment import handle_issue_comment, handle_pr_review_comment
from django_github_app.routing import GitHubRouter

pytestmark = [pytest.mark.django_db]


@pytest.fixture
def mock_dispatch():
    with patch.object(GitHubRouter, 'dispatch_commands') as mock:
        yield mock


def test_handle_issue_comment(mock_dispatch):
    """Test that issue comments correctly identify issue vs PR comments."""
    # Setup - Issue comment
    issue_data = {
        "comment": {"body": "@app command"},
        "issue": {}  # No PR field
    }
    issue_event = sansio.Event(issue_data, event="issue_comment", delivery_id="1234")
    
    # Setup - PR comment (via issue_comment event)
    pr_data = {
        "comment": {"body": "@app command"},
        "issue": {"pull_request": {}}  # Has PR field
    }
    pr_event = sansio.Event(pr_data, event="issue_comment", delivery_id="5678")
    
    gh = MagicMock()
    
    # Test
    handle_issue_comment(issue_event, gh)
    handle_issue_comment(pr_event, gh)
    
    # Assert
    assert mock_dispatch.call_count == 2
    
    # First call should be for issue
    issue_call = mock_dispatch.call_args_list[0]
    assert issue_call[1]["is_issue"] is True
    assert issue_call[1]["is_pull_request"] is False
    
    # Second call should be for PR
    pr_call = mock_dispatch.call_args_list[1]
    assert pr_call[1]["is_issue"] is False
    assert pr_call[1]["is_pull_request"] is True


def test_handle_pr_review_comment(mock_dispatch):
    """Test that PR review comments are correctly identified as PRs."""
    # Setup
    data = {
        "comment": {"body": "@app command"},
    }
    event = sansio.Event(data, event="pull_request_review_comment", delivery_id="1234")
    gh = MagicMock()
    
    # Test
    handle_pr_review_comment(event, gh)
    
    # Assert
    mock_dispatch.assert_called_once()
    # Should always be a PR
    assert mock_dispatch.call_args[1]["is_pull_request"] is True
    assert "is_issue" not in mock_dispatch.call_args[1] or mock_dispatch.call_args[1]["is_issue"] is False


# Test file: tests/events/test_acomment.py

from __future__ import annotations

import pytest
from gidgethub import sansio
from unittest.mock import AsyncMock, patch

from django_github_app.events.acomment import ahandle_issue_comment, ahandle_pr_review_comment
from django_github_app.routing import GitHubRouter

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db]


@pytest.fixture
async def mock_adispatch():
    with patch.object(GitHubRouter, 'adispatch_commands', new_callable=AsyncMock) as mock:
        yield mock


async def test_ahandle_issue_comment(mock_adispatch):
    """Test that async issue comments correctly identify issue vs PR comments."""
    # Setup - Issue comment
    issue_data = {
        "comment": {"body": "@app command"},
        "issue": {}  # No PR field
    }
    issue_event = sansio.Event(issue_data, event="issue_comment", delivery_id="1234")
    
    # Setup - PR comment (via issue_comment event)
    pr_data = {
        "comment": {"body": "@app command"},
        "issue": {"pull_request": {}}  # Has PR field
    }
    pr_event = sansio.Event(pr_data, event="issue_comment", delivery_id="5678")
    
    gh = AsyncMock()
    
    # Test
    await ahandle_issue_comment(issue_event, gh)
    await ahandle_issue_comment(pr_event, gh)
    
    # Assert
    assert mock_adispatch.call_count == 2
    
    # First call should be for issue
    issue_call = mock_adispatch.call_args_list[0]
    assert issue_call[1]["is_issue"] is True
    assert issue_call[1]["is_pull_request"] is False
    
    # Second call should be for PR
    pr_call = mock_adispatch.call_args_list[1]
    assert pr_call[1]["is_issue"] is False
    assert pr_call[1]["is_pull_request"] is True


async def test_ahandle_pr_review_comment(mock_adispatch):
    """Test that async PR review comments are correctly identified as PRs."""
    # Setup
    data = {
        "comment": {"body": "@app command"},
    }
    event = sansio.Event(data, event="pull_request_review_comment", delivery_id="1234")
    gh = AsyncMock()
    
    # Test
    await ahandle_pr_review_comment(event, gh)
    
    # Assert
    mock_adispatch.assert_called_once()
    # Should always be a PR
    assert mock_adispatch.call_args[1]["is_pull_request"] is True
    assert "is_issue" not in mock_adispatch.call_args[1] or mock_adispatch.call_args[1]["is_issue"] is False


# Test file: tests/test_integration.py

from __future__ import annotations

import pytest
from gidgethub import sansio
from unittest.mock import MagicMock, AsyncMock

from django_github_app.conf import app_settings
from django_github_app.routing import GitHubRouter
from django_github_app.views import SyncWebhookView, AsyncWebhookView
from django_github_app.events.handlers import comment
from django_github_app.events.ahandlers import acomment

pytestmark = [pytest.mark.django_db]


@pytest.fixture
def app_name(override_app_settings):
    with override_app_settings(NAME="test-app"):
        yield app_settings.NAME


class TestCommandIntegration:
    """End-to-end integration tests for command functionality."""
    
    def test_command_handler_registration(self, app_name):
        """Test that command handlers can be registered and found."""
        router = GitHubRouter()
        
        # Register a command handler
        command_called = False
        
        @router.command("test")
        def handle_test_command(event, gh, args):
            nonlocal command_called
            command_called = True
            assert args == "arg1 arg2"
        
        # Create an event with a command
        data = {
            "comment": {"body": f"@{app_name} test arg1 arg2"},
            "issue": {}
        }
        event = sansio.Event(data, event="issue_comment", delivery_id="1234")
        gh = MagicMock()
        
        # Process the event
        router.dispatch_commands(event, gh, app_name, is_issue=True)
        
        # Verify the command was called
        assert command_called
    
    @pytest.mark.asyncio
    async def test_async_webhook_view_with_command(self, app_name, monkeypatch):
        """Test that commands are processed through the async webhook view."""
        # Mock GitHubRouter.adispatch
        original_adispatch = GitHubRouter.adispatch
        adispatch_called = False
        
        async def mock_adispatch(self, event, *args, **kwargs):
            nonlocal adispatch_called
            adispatch_called = True
            # Call the original method to ensure normal processing
            await original_adispatch(self, event, *args, **kwargs)
        
        monkeypatch.setattr(GitHubRouter, "adispatch", mock_adispatch)
        
        # Set up a command handler
        router = GitHubRouter()
        command_called = False
        
        @router.command("test")
        async def handle_test_command(event, gh, args):
            nonlocal command_called
            command_called = True
        
        # Create an issue_comment event
        data = {
            "comment": {"body": f"@{app_name} test"},
            "issue": {}
        }
        event = sansio.Event(data, event="issue_comment", delivery_id="1234")
        
        # Create a mock GitHub API
        gh = AsyncMock()
        
        # Manually call the acomment handler (which would be triggered by the webhook view)
        await acomment.ahandle_issue_comment(event, gh)
        
        # Verify the dispatch was called and the command was processed
        assert adispatch_called
        assert command_called
```

## Step 5: Prepare PR Description
**Status:** Completed ✅

### PR Title:
Add support for handling commands in comments via @mentions

### PR Description:
Fixes #15

Changes:
- Added a command registration system to GitHubRouter with `@gh.command()` decorator
- Implemented command extraction from comments that mention the app
- Added handlers for issue_comment and pull_request_review_comment events
- Created support for both sync and async command handlers
- Added ability to scope commands to issues and/or pull requests
- Extended existing lazy loading mechanism to include new comment handlers

Rationale:
This solution enables GitHub Apps to respond to commands in comments similar to how Dependabot works. The implementation follows the established patterns in the codebase, maintaining consistency with the existing event handling system. The command processing is lightweight and only activates when relevant comments are posted, ensuring minimal performance impact.

Affected Components:
- Router: Extended to support command registration and dispatch
- Event handlers: Added comment and review comment event handling
- Async support: Full support for both sync and async command handling

Testing:
- Unit tests for command extraction, registration, and dispatch
- Tests for proper issue vs PR detection in comments
- Tests for handler scoping (issue-only, PR-only, or both)
- Integration tests for full command handling flow
- Comprehensive test coverage for both sync and async paths

Considerations:
- GitHub App needs the appropriate permissions to read issue/PR comments
- Developers need to subscribe to issue_comment and/or pull_request_review_comment events
- Command parsing uses regex with proper escaping for security
- Maintains backward compatibility with existing event handling

Follow-up Tasks:
- Add documentation with examples of command usage
- Consider adding support for command aliases
- Explore adding subcommand support for more complex interactions

## Progress Tracker:
- [x] Step 1: Understand the Issue
- [x] Step 2: Locate Relevant Code
- [x] Step 3: Implement Solution
- [x] Step 4: Add Tests
- [x] Step 5: Prepare PR Description

## 🎉 Issue Resolution Complete 🎉
All steps have been completed to resolve issue #15. The full PR description has been prepared and all necessary code changes and tests have been proposed.