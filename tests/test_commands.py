from __future__ import annotations

from gidgethub import sansio

from django_github_app.commands import CommandScope
from django_github_app.commands import check_event_for_mention
from django_github_app.commands import check_event_scope
from django_github_app.commands import parse_mentions


class TestParseMentions:
    def test_simple_mention_with_command(self):
        text = "@mybot help"
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].mention == "@mybot"
        assert mentions[0].command == "help"

    def test_mention_without_command(self):
        text = "@mybot"
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].mention == "@mybot"
        assert mentions[0].command is None

    def test_case_insensitive_matching(self):
        text = "@MyBot help"
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].mention == "@MyBot"
        assert mentions[0].command == "help"

    def test_command_case_normalization(self):
        text = "@mybot HELP"
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "help"

    def test_multiple_mentions(self):
        text = "@mybot help and then @mybot deploy"
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 2
        assert mentions[0].command == "help"
        assert mentions[1].command == "deploy"

    def test_ignore_other_mentions(self):
        text = "@otheruser help @mybot deploy @someone else"
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "deploy"

    def test_mention_in_code_block(self):
        text = """
        Here's some text
        ```
        @mybot help
        ```
        @mybot deploy
        """
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "deploy"

    def test_mention_in_inline_code(self):
        text = "Use `@mybot help` for help, or just @mybot deploy"
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "deploy"

    def test_mention_in_quote(self):
        text = """
        > @mybot help
        @mybot deploy
        """
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "deploy"

    def test_empty_text(self):
        mentions = parse_mentions("", "mybot")

        assert mentions == []

    def test_none_text(self):
        mentions = parse_mentions(None, "mybot")

        assert mentions == []

    def test_mention_at_start_of_line(self):
        text = "@mybot help"
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "help"

    def test_mention_in_middle_of_text(self):
        text = "Hey @mybot help me"
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "help"

    def test_mention_with_punctuation_after(self):
        text = "@mybot help!"
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "help"

    def test_hyphenated_username(self):
        text = "@my-bot help"
        mentions = parse_mentions(text, "my-bot")

        assert len(mentions) == 1
        assert mentions[0].mention == "@my-bot"
        assert mentions[0].command == "help"

    def test_underscore_username(self):
        text = "@my_bot help"
        mentions = parse_mentions(text, "my_bot")

        assert len(mentions) == 1
        assert mentions[0].mention == "@my_bot"
        assert mentions[0].command == "help"

    def test_no_space_after_mention(self):
        text = "@mybot, please help"
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command is None

    def test_multiple_spaces_before_command(self):
        text = "@mybot    help"
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "help"

    def test_hyphenated_command(self):
        text = "@mybot async-test"
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "async-test"

    def test_special_character_command(self):
        text = "@mybot ?"
        mentions = parse_mentions(text, "mybot")

        assert len(mentions) == 1
        assert mentions[0].command == "?"


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


class TestCheckEventScope:
    def test_no_scope_allows_all_events(self):
        # When no scope is specified, all events should pass
        event1 = sansio.Event({"issue": {}}, event="issue_comment", delivery_id="1")
        assert check_event_scope(event1, None) is True

        event2 = sansio.Event({}, event="pull_request_review_comment", delivery_id="2")
        assert check_event_scope(event2, None) is True

        event3 = sansio.Event({}, event="commit_comment", delivery_id="3")
        assert check_event_scope(event3, None) is True

    def test_issue_scope_on_issue_comment(self):
        # Issue comment on an actual issue (no pull_request field)
        issue_event = sansio.Event(
            {"issue": {"title": "Bug report"}}, event="issue_comment", delivery_id="1"
        )
        assert check_event_scope(issue_event, CommandScope.ISSUE) is True

        # Issue comment on a pull request (has pull_request field)
        pr_event = sansio.Event(
            {"issue": {"title": "PR title", "pull_request": {"url": "..."}}},
            event="issue_comment",
            delivery_id="2",
        )
        assert check_event_scope(pr_event, CommandScope.ISSUE) is False

    def test_pr_scope_on_issue_comment(self):
        # Issue comment on an actual issue (no pull_request field)
        issue_event = sansio.Event(
            {"issue": {"title": "Bug report"}}, event="issue_comment", delivery_id="1"
        )
        assert check_event_scope(issue_event, CommandScope.PR) is False

        # Issue comment on a pull request (has pull_request field)
        pr_event = sansio.Event(
            {"issue": {"title": "PR title", "pull_request": {"url": "..."}}},
            event="issue_comment",
            delivery_id="2",
        )
        assert check_event_scope(pr_event, CommandScope.PR) is True

    def test_pr_scope_allows_pr_specific_events(self):
        # PR scope should allow pull_request_review_comment
        event1 = sansio.Event({}, event="pull_request_review_comment", delivery_id="1")
        assert check_event_scope(event1, CommandScope.PR) is True

        # PR scope should allow pull_request_review
        event2 = sansio.Event({}, event="pull_request_review", delivery_id="2")
        assert check_event_scope(event2, CommandScope.PR) is True

        # PR scope should not allow commit_comment
        event3 = sansio.Event({}, event="commit_comment", delivery_id="3")
        assert check_event_scope(event3, CommandScope.PR) is False

    def test_commit_scope_allows_commit_comment_only(self):
        # Commit scope should allow commit_comment
        event1 = sansio.Event({}, event="commit_comment", delivery_id="1")
        assert check_event_scope(event1, CommandScope.COMMIT) is True

        # Commit scope should not allow issue_comment
        event2 = sansio.Event({"issue": {}}, event="issue_comment", delivery_id="2")
        assert check_event_scope(event2, CommandScope.COMMIT) is False

        # Commit scope should not allow PR events
        event3 = sansio.Event({}, event="pull_request_review_comment", delivery_id="3")
        assert check_event_scope(event3, CommandScope.COMMIT) is False

    def test_issue_scope_disallows_non_issue_events(self):
        # Issue scope should not allow pull_request_review_comment
        event1 = sansio.Event({}, event="pull_request_review_comment", delivery_id="1")
        assert check_event_scope(event1, CommandScope.ISSUE) is False

        # Issue scope should not allow commit_comment
        event2 = sansio.Event({}, event="commit_comment", delivery_id="2")
        assert check_event_scope(event2, CommandScope.ISSUE) is False

    def test_pull_request_field_none_treated_as_issue(self):
        # If pull_request field exists but is None, treat as issue
        event = sansio.Event(
            {"issue": {"title": "Issue", "pull_request": None}},
            event="issue_comment",
            delivery_id="1",
        )
        assert check_event_scope(event, CommandScope.ISSUE) is True
        assert check_event_scope(event, CommandScope.PR) is False

    def test_missing_issue_data(self):
        # If issue data is missing entirely, default behavior
        event = sansio.Event({}, event="issue_comment", delivery_id="1")
        assert check_event_scope(event, CommandScope.ISSUE) is True
        assert check_event_scope(event, CommandScope.PR) is False
