from __future__ import annotations

import pytest
from gidgethub import sansio

from django_github_app.mentions import MentionScope
from django_github_app.mentions import check_event_for_mention
from django_github_app.mentions import get_commands
from django_github_app.mentions import get_event_scope
from django_github_app.mentions import parse_mentions


@pytest.fixture
def create_comment_event():
    """Fixture to create comment events for testing."""

    def _create(body: str) -> sansio.Event:
        return sansio.Event(
            {"comment": {"body": body}}, event="issue_comment", delivery_id="test"
        )

    return _create


class TestParseMentions:
    def test_simple_mention_with_command(self, create_comment_event):
        event = create_comment_event("@mybot help")
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].mention == "@mybot"
        assert mentions[0].command == "help"

    def test_mention_without_command(self, create_comment_event):
        event = create_comment_event("@mybot")
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].mention == "@mybot"
        assert mentions[0].command is None

    def test_case_insensitive_matching(self, create_comment_event):
        event = create_comment_event("@MyBot help")
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].mention == "@MyBot"
        assert mentions[0].command == "help"

    def test_command_case_normalization(self, create_comment_event):
        event = create_comment_event("@mybot HELP")
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "help"

    def test_multiple_mentions(self, create_comment_event):
        event = create_comment_event("@mybot help and then @mybot deploy")
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 2
        assert mentions[0].command == "help"
        assert mentions[1].command == "deploy"

    def test_ignore_other_mentions(self, create_comment_event):
        event = create_comment_event("@otheruser help @mybot deploy @someone else")
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "deploy"

    def test_mention_in_code_block(self, create_comment_event):
        text = """
        Here's some text
        ```
        @mybot help
        ```
        @mybot deploy
        """
        event = create_comment_event(text)
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "deploy"

    def test_mention_in_inline_code(self, create_comment_event):
        event = create_comment_event(
            "Use `@mybot help` for help, or just @mybot deploy"
        )
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "deploy"

    def test_mention_in_quote(self, create_comment_event):
        text = """
        > @mybot help
        @mybot deploy
        """
        event = create_comment_event(text)
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "deploy"

    def test_empty_text(self, create_comment_event):
        event = create_comment_event("")
        mentions = parse_mentions(event, "mybot")

        assert mentions == []

    def test_none_text(self, create_comment_event):
        # Create an event with no comment body
        event = sansio.Event({}, event="issue_comment", delivery_id="test")
        mentions = parse_mentions(event, "mybot")

        assert mentions == []

    def test_mention_at_start_of_line(self, create_comment_event):
        event = create_comment_event("@mybot help")
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "help"

    def test_mention_in_middle_of_text(self, create_comment_event):
        event = create_comment_event("Hey @mybot help me")
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "help"

    def test_mention_with_punctuation_after(self, create_comment_event):
        event = create_comment_event("@mybot help!")
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "help"

    def test_hyphenated_username(self, create_comment_event):
        event = create_comment_event("@my-bot help")
        mentions = parse_mentions(event, "my-bot")

        assert len(mentions) == 1
        assert mentions[0].mention == "@my-bot"
        assert mentions[0].command == "help"

    def test_underscore_username(self, create_comment_event):
        event = create_comment_event("@my_bot help")
        mentions = parse_mentions(event, "my_bot")

        assert len(mentions) == 1
        assert mentions[0].mention == "@my_bot"
        assert mentions[0].command == "help"

    def test_no_space_after_mention(self, create_comment_event):
        event = create_comment_event("@mybot, please help")
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command is None

    def test_multiple_spaces_before_command(self, create_comment_event):
        event = create_comment_event("@mybot    help")
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "help"

    def test_hyphenated_command(self, create_comment_event):
        event = create_comment_event("@mybot async-test")
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "async-test"

    def test_special_character_command(self, create_comment_event):
        event = create_comment_event("@mybot ?")
        mentions = parse_mentions(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "?"


class TestGetCommands:
    def test_single_command(self, create_comment_event):
        event = create_comment_event("@bot deploy")
        commands = get_commands(event, "bot")
        assert commands == ["deploy"]

    def test_multiple_commands(self, create_comment_event):
        event = create_comment_event("@bot help and @bot deploy and @bot test")
        commands = get_commands(event, "bot")
        assert commands == ["help", "deploy", "test"]

    def test_no_commands(self, create_comment_event):
        event = create_comment_event("@bot")
        commands = get_commands(event, "bot")
        assert commands == []

    def test_no_mentions(self, create_comment_event):
        event = create_comment_event("Just a regular comment")
        commands = get_commands(event, "bot")
        assert commands == []

    def test_mentions_of_other_users(self, create_comment_event):
        event = create_comment_event("@otheruser deploy @bot help")
        commands = get_commands(event, "bot")
        assert commands == ["help"]

    def test_case_normalization(self, create_comment_event):
        event = create_comment_event("@bot DEPLOY")
        commands = get_commands(event, "bot")
        assert commands == ["deploy"]


class TestCheckMentionMatches:
    def test_match_with_command(self):
        event = sansio.Event(
            {"comment": {"body": "@bot help"}}, event="issue_comment", delivery_id="123"
        )

        assert check_event_for_mention(event, "help", "bot") is True
        assert check_event_for_mention(event, "deploy", "bot") is False

    def test_match_without_command(self):
        event = sansio.Event(
            {"comment": {"body": "@bot help"}}, event="issue_comment", delivery_id="123"
        )

        assert check_event_for_mention(event, None, "bot") is True

        event = sansio.Event(
            {"comment": {"body": "no mention here"}},
            event="issue_comment",
            delivery_id="124",
        )

        assert check_event_for_mention(event, None, "bot") is False

    def test_no_comment_body(self):
        event = sansio.Event({}, event="issue_comment", delivery_id="123")

        assert check_event_for_mention(event, "help", "bot") is False

        event = sansio.Event({"comment": {}}, event="issue_comment", delivery_id="124")

        assert check_event_for_mention(event, "help", "bot") is False

    def test_case_insensitive_command_match(self):
        event = sansio.Event(
            {"comment": {"body": "@bot HELP"}}, event="issue_comment", delivery_id="123"
        )

        assert check_event_for_mention(event, "help", "bot") is True
        assert check_event_for_mention(event, "HELP", "bot") is True

    def test_multiple_mentions(self):
        event = sansio.Event(
            {"comment": {"body": "@bot help @bot deploy"}},
            event="issue_comment",
            delivery_id="123",
        )

        assert check_event_for_mention(event, "help", "bot") is True
        assert check_event_for_mention(event, "deploy", "bot") is True
        assert check_event_for_mention(event, "test", "bot") is False


class TestGetEventScope:
    def test_get_event_scope_for_various_events(self):
        # Issue comment on actual issue
        event1 = sansio.Event({"issue": {}}, event="issue_comment", delivery_id="1")
        assert get_event_scope(event1) == MentionScope.ISSUE

        # PR review comment
        event2 = sansio.Event({}, event="pull_request_review_comment", delivery_id="2")
        assert get_event_scope(event2) == MentionScope.PR

        # Commit comment
        event3 = sansio.Event({}, event="commit_comment", delivery_id="3")
        assert get_event_scope(event3) == MentionScope.COMMIT

    def test_issue_scope_on_issue_comment(self):
        # Issue comment on an actual issue (no pull_request field)
        issue_event = sansio.Event(
            {"issue": {"title": "Bug report"}}, event="issue_comment", delivery_id="1"
        )
        assert get_event_scope(issue_event) == MentionScope.ISSUE

        # Issue comment on a pull request (has pull_request field)
        pr_event = sansio.Event(
            {"issue": {"title": "PR title", "pull_request": {"url": "..."}}},
            event="issue_comment",
            delivery_id="2",
        )
        assert get_event_scope(pr_event) == MentionScope.PR

    def test_pr_scope_on_issue_comment(self):
        # Issue comment on an actual issue (no pull_request field)
        issue_event = sansio.Event(
            {"issue": {"title": "Bug report"}}, event="issue_comment", delivery_id="1"
        )
        assert get_event_scope(issue_event) == MentionScope.ISSUE

        # Issue comment on a pull request (has pull_request field)
        pr_event = sansio.Event(
            {"issue": {"title": "PR title", "pull_request": {"url": "..."}}},
            event="issue_comment",
            delivery_id="2",
        )
        assert get_event_scope(pr_event) == MentionScope.PR

    def test_pr_scope_allows_pr_specific_events(self):
        # PR scope should allow pull_request_review_comment
        event1 = sansio.Event({}, event="pull_request_review_comment", delivery_id="1")
        assert get_event_scope(event1) == MentionScope.PR

        # PR scope should allow pull_request_review
        event2 = sansio.Event({}, event="pull_request_review", delivery_id="2")
        assert get_event_scope(event2) == MentionScope.PR

        # PR scope should not allow commit_comment
        event3 = sansio.Event({}, event="commit_comment", delivery_id="3")
        assert get_event_scope(event3) == MentionScope.COMMIT

    def test_commit_scope_allows_commit_comment_only(self):
        # Commit scope should allow commit_comment
        event1 = sansio.Event({}, event="commit_comment", delivery_id="1")
        assert get_event_scope(event1) == MentionScope.COMMIT

        # Commit scope should not allow issue_comment
        event2 = sansio.Event({"issue": {}}, event="issue_comment", delivery_id="2")
        assert get_event_scope(event2) == MentionScope.ISSUE

        # Commit scope should not allow PR events
        event3 = sansio.Event({}, event="pull_request_review_comment", delivery_id="3")
        assert get_event_scope(event3) == MentionScope.PR

    def test_different_event_types_have_correct_scope(self):
        # pull_request_review_comment should be PR scope
        event1 = sansio.Event({}, event="pull_request_review_comment", delivery_id="1")
        assert get_event_scope(event1) == MentionScope.PR

        # commit_comment should be COMMIT scope
        event2 = sansio.Event({}, event="commit_comment", delivery_id="2")
        assert get_event_scope(event2) == MentionScope.COMMIT

    def test_pull_request_field_none_treated_as_issue(self):
        # If pull_request field exists but is None, treat as issue
        event = sansio.Event(
            {"issue": {"title": "Issue", "pull_request": None}},
            event="issue_comment",
            delivery_id="1",
        )
        assert get_event_scope(event) == MentionScope.ISSUE

    def test_missing_issue_data(self):
        # If issue data is missing entirely, defaults to ISSUE scope for issue_comment
        event = sansio.Event({}, event="issue_comment", delivery_id="1")
        assert get_event_scope(event) == MentionScope.ISSUE

    def test_unknown_event_returns_none(self):
        # Unknown event types should return None
        event = sansio.Event({}, event="unknown_event", delivery_id="1")
        assert get_event_scope(event) is None
