from __future__ import annotations

import re

import pytest
from django.utils import timezone
from gidgethub import sansio

from django_github_app.mentions import Comment
from django_github_app.mentions import MentionScope
from django_github_app.mentions import check_pattern_match
from django_github_app.mentions import parse_mentions_for_username


@pytest.fixture
def create_comment_event():
    def _create(body: str) -> sansio.Event:
        return sansio.Event(
            {"comment": {"body": body}}, event="issue_comment", delivery_id="test"
        )

    return _create


class TestParseMentions:
    def test_simple_mention_with_command(self, create_comment_event):
        event = create_comment_event("@mybot help")
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].username == "mybot"
        assert mentions[0].text == "help"
        assert mentions[0].position == 0
        assert mentions[0].line_number == 1

    def test_mention_without_command(self, create_comment_event):
        event = create_comment_event("@mybot")
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].username == "mybot"
        assert mentions[0].text == ""

    def test_case_insensitive_matching(self, create_comment_event):
        event = create_comment_event("@MyBot help")
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].username == "MyBot"  # Username is preserved as found
        assert mentions[0].text == "help"

    def test_command_case_normalization(self, create_comment_event):
        event = create_comment_event("@mybot HELP")
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        # Command case is preserved in text, normalization happens elsewhere
        assert mentions[0].text == "HELP"

    def test_multiple_mentions(self, create_comment_event):
        event = create_comment_event("@mybot help and then @mybot deploy")
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 2
        assert mentions[0].text == "help and then"
        assert mentions[1].text == "deploy"

    def test_ignore_other_mentions(self, create_comment_event):
        event = create_comment_event("@otheruser help @mybot deploy @someone else")
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "deploy @someone else"

    def test_mention_in_code_block(self, create_comment_event):
        text = """
        Here's some text
        ```
        @mybot help
        ```
        @mybot deploy
        """
        event = create_comment_event(text)
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "deploy"

    def test_mention_in_inline_code(self, create_comment_event):
        event = create_comment_event(
            "Use `@mybot help` for help, or just @mybot deploy"
        )
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "deploy"

    def test_mention_in_quote(self, create_comment_event):
        text = """
        > @mybot help
        @mybot deploy
        """
        event = create_comment_event(text)
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "deploy"

    def test_empty_text(self, create_comment_event):
        event = create_comment_event("")
        mentions = parse_mentions_for_username(event, "mybot")

        assert mentions == []

    def test_none_text(self, create_comment_event):
        # Create an event with no comment body
        event = sansio.Event({}, event="issue_comment", delivery_id="test")
        mentions = parse_mentions_for_username(event, "mybot")

        assert mentions == []

    def test_mention_at_start_of_line(self, create_comment_event):
        event = create_comment_event("@mybot help")
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "help"

    def test_mention_in_middle_of_text(self, create_comment_event):
        event = create_comment_event("Hey @mybot help me")
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "help me"

    def test_mention_with_punctuation_after(self, create_comment_event):
        event = create_comment_event("@mybot help!")
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "help!"

    def test_hyphenated_username(self, create_comment_event):
        event = create_comment_event("@my-bot help")
        mentions = parse_mentions_for_username(event, "my-bot")

        assert len(mentions) == 1
        assert mentions[0].username == "my-bot"
        assert mentions[0].text == "help"

    def test_underscore_username(self, create_comment_event):
        event = create_comment_event("@my_bot help")
        mentions = parse_mentions_for_username(event, "my_bot")

        assert len(mentions) == 1
        assert mentions[0].username == "my_bot"
        assert mentions[0].text == "help"

    def test_no_space_after_mention(self, create_comment_event):
        event = create_comment_event("@mybot, please help")
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == ", please help"

    def test_multiple_spaces_before_command(self, create_comment_event):
        event = create_comment_event("@mybot    help")
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "help"  # Whitespace is stripped

    def test_hyphenated_command(self, create_comment_event):
        event = create_comment_event("@mybot async-test")
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "async-test"

    def test_special_character_command(self, create_comment_event):
        event = create_comment_event("@mybot ?")
        mentions = parse_mentions_for_username(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "?"


class TestGetEventScope:
    def test_from_event_for_various_events(self):
        event1 = sansio.Event({"issue": {}}, event="issue_comment", delivery_id="1")
        assert MentionScope.from_event(event1) == MentionScope.ISSUE

        event2 = sansio.Event({}, event="pull_request_review_comment", delivery_id="2")
        assert MentionScope.from_event(event2) == MentionScope.PR

        event3 = sansio.Event({}, event="commit_comment", delivery_id="3")
        assert MentionScope.from_event(event3) == MentionScope.COMMIT

    def test_issue_scope_on_issue_comment(self):
        issue_event = sansio.Event(
            {"issue": {"title": "Bug report"}}, event="issue_comment", delivery_id="1"
        )
        assert MentionScope.from_event(issue_event) == MentionScope.ISSUE

        pr_event = sansio.Event(
            {"issue": {"title": "PR title", "pull_request": {"url": "..."}}},
            event="issue_comment",
            delivery_id="2",
        )
        assert MentionScope.from_event(pr_event) == MentionScope.PR

    def test_pr_scope_on_issue_comment(self):
        issue_event = sansio.Event(
            {"issue": {"title": "Bug report"}}, event="issue_comment", delivery_id="1"
        )
        assert MentionScope.from_event(issue_event) == MentionScope.ISSUE

        pr_event = sansio.Event(
            {"issue": {"title": "PR title", "pull_request": {"url": "..."}}},
            event="issue_comment",
            delivery_id="2",
        )
        assert MentionScope.from_event(pr_event) == MentionScope.PR

    def test_pr_scope_allows_pr_specific_events(self):
        event1 = sansio.Event({}, event="pull_request_review_comment", delivery_id="1")
        assert MentionScope.from_event(event1) == MentionScope.PR

        event2 = sansio.Event({}, event="pull_request_review", delivery_id="2")
        assert MentionScope.from_event(event2) == MentionScope.PR

        event3 = sansio.Event({}, event="commit_comment", delivery_id="3")
        assert MentionScope.from_event(event3) == MentionScope.COMMIT

    def test_commit_scope_allows_commit_comment_only(self):
        event1 = sansio.Event({}, event="commit_comment", delivery_id="1")
        assert MentionScope.from_event(event1) == MentionScope.COMMIT

        event2 = sansio.Event({"issue": {}}, event="issue_comment", delivery_id="2")
        assert MentionScope.from_event(event2) == MentionScope.ISSUE

        event3 = sansio.Event({}, event="pull_request_review_comment", delivery_id="3")
        assert MentionScope.from_event(event3) == MentionScope.PR

    def test_different_event_types_have_correct_scope(self):
        event1 = sansio.Event({}, event="pull_request_review_comment", delivery_id="1")
        assert MentionScope.from_event(event1) == MentionScope.PR

        event2 = sansio.Event({}, event="commit_comment", delivery_id="2")
        assert MentionScope.from_event(event2) == MentionScope.COMMIT

    def test_pull_request_field_none_treated_as_issue(self):
        event = sansio.Event(
            {"issue": {"title": "Issue", "pull_request": None}},
            event="issue_comment",
            delivery_id="1",
        )
        assert MentionScope.from_event(event) == MentionScope.ISSUE

    def test_missing_issue_data(self):
        event = sansio.Event({}, event="issue_comment", delivery_id="1")
        assert MentionScope.from_event(event) == MentionScope.ISSUE

    def test_unknown_event_returns_none(self):
        event = sansio.Event({}, event="unknown_event", delivery_id="1")
        assert MentionScope.from_event(event) is None


class TestComment:
    def test_from_event_issue_comment(self):
        event = sansio.Event(
            {
                "comment": {
                    "body": "This is a test comment",
                    "user": {"login": "testuser"},
                    "created_at": "2024-01-01T12:00:00Z",
                    "html_url": "https://github.com/test/repo/issues/1#issuecomment-123",
                }
            },
            event="issue_comment",
            delivery_id="test-1",
        )

        comment = Comment.from_event(event)

        assert comment.body == "This is a test comment"
        assert comment.author == "testuser"
        assert comment.created_at.isoformat() == "2024-01-01T12:00:00+00:00"
        assert comment.url == "https://github.com/test/repo/issues/1#issuecomment-123"
        assert comment.mentions == []
        assert comment.line_count == 1

    def test_from_event_pull_request_review_comment(self):
        event = sansio.Event(
            {
                "comment": {
                    "body": "Line 1\nLine 2\nLine 3",
                    "user": {"login": "reviewer"},
                    "created_at": "2024-02-15T14:30:00Z",
                    "html_url": "https://github.com/test/repo/pull/5#discussion_r123",
                }
            },
            event="pull_request_review_comment",
            delivery_id="test-2",
        )

        comment = Comment.from_event(event)

        assert comment.body == "Line 1\nLine 2\nLine 3"
        assert comment.author == "reviewer"
        assert comment.url == "https://github.com/test/repo/pull/5#discussion_r123"
        assert comment.line_count == 3

    def test_from_event_pull_request_review(self):
        event = sansio.Event(
            {
                "review": {
                    "body": "LGTM!",
                    "user": {"login": "approver"},
                    "created_at": "2024-03-10T09:15:00Z",
                    "html_url": "https://github.com/test/repo/pull/10#pullrequestreview-123",
                }
            },
            event="pull_request_review",
            delivery_id="test-3",
        )

        comment = Comment.from_event(event)

        assert comment.body == "LGTM!"
        assert comment.author == "approver"
        assert (
            comment.url == "https://github.com/test/repo/pull/10#pullrequestreview-123"
        )

    def test_from_event_commit_comment(self):
        event = sansio.Event(
            {
                "comment": {
                    "body": "Nice commit!",
                    "user": {"login": "commenter"},
                    "created_at": "2024-04-20T16:45:00Z",
                    "html_url": "https://github.com/test/repo/commit/abc123#commitcomment-456",
                }
            },
            event="commit_comment",
            delivery_id="test-4",
        )

        comment = Comment.from_event(event)

        assert comment.body == "Nice commit!"
        assert comment.author == "commenter"
        assert (
            comment.url
            == "https://github.com/test/repo/commit/abc123#commitcomment-456"
        )

    def test_from_event_missing_fields(self):
        event = sansio.Event(
            {
                "comment": {
                    "body": "Minimal comment",
                    # Missing user, created_at, html_url
                },
                "sender": {"login": "fallback-user"},
            },
            event="issue_comment",
            delivery_id="test-5",
        )

        comment = Comment.from_event(event)

        assert comment.body == "Minimal comment"
        assert comment.author == "fallback-user"
        assert comment.url == ""
        # created_at should be roughly now
        assert (timezone.now() - comment.created_at).total_seconds() < 5

    def test_from_event_invalid_event_type(self):
        event = sansio.Event(
            {"some_data": "value"},
            event="push",
            delivery_id="test-6",
        )

        with pytest.raises(
            ValueError, match="Cannot extract comment from event type: push"
        ):
            Comment.from_event(event)

    @pytest.mark.parametrize(
        "body,line_count",
        [
            ("Single line", 1),
            ("Line 1\nLine 2\nLine 3", 3),
            ("Line 1\n\nLine 3", 3),
            ("", 0),
        ],
    )
    def test_line_count_property(self, body, line_count):
        comment = Comment(
            body=body,
            author="user",
            created_at=timezone.now(),
            url="",
            mentions=[],
        )
        assert comment.line_count == line_count

    def test_from_event_timezone_handling(self):
        event = sansio.Event(
            {
                "comment": {
                    "body": "Test",
                    "user": {"login": "user"},
                    "created_at": "2024-01-01T12:00:00Z",
                    "html_url": "",
                }
            },
            event="issue_comment",
            delivery_id="test-7",
        )

        comment = Comment.from_event(event)

        # Check that the datetime is timezone-aware (UTC)
        assert comment.created_at.tzinfo is not None
        assert comment.created_at.isoformat() == "2024-01-01T12:00:00+00:00"


class TestPatternMatching:
    def test_check_pattern_match_none(self):
        match = check_pattern_match("any text", None)

        assert match is not None
        assert match.group(0) == "any text"

    def test_check_pattern_match_literal_string(self):
        # Matching case
        match = check_pattern_match("deploy production", "deploy")
        assert match is not None
        assert match.group(0) == "deploy"

        # Case insensitive
        match = check_pattern_match("DEPLOY production", "deploy")
        assert match is not None

        # No match
        match = check_pattern_match("help me", "deploy")
        assert match is None

        # Must start with pattern
        match = check_pattern_match("please deploy", "deploy")
        assert match is None

    def test_check_pattern_match_regex(self):
        # Simple regex
        match = check_pattern_match("deploy prod", re.compile(r"deploy (prod|staging)"))
        assert match is not None
        assert match.group(0) == "deploy prod"
        assert match.group(1) == "prod"

        # Named groups
        match = check_pattern_match(
            "deploy-prod", re.compile(r"deploy-(?P<env>prod|staging|dev)")
        )
        assert match is not None
        assert match.group("env") == "prod"

        # Question mark pattern
        match = check_pattern_match("can you help?", re.compile(r".*\?$"))
        assert match is not None

        # No match
        match = check_pattern_match("deploy test", re.compile(r"deploy (prod|staging)"))
        assert match is None

    def test_check_pattern_match_invalid_regex(self):
        # Invalid regex should be treated as literal
        match = check_pattern_match("test [invalid", "[invalid")
        assert match is None  # Doesn't start with [invalid

        match = check_pattern_match("[invalid regex", "[invalid")
        assert match is not None  # Starts with literal [invalid

    def test_check_pattern_match_flag_preservation(self):
        # Case-sensitive pattern
        pattern_cs = re.compile(r"DEPLOY", re.MULTILINE)
        match = check_pattern_match("deploy", pattern_cs)
        assert match is None  # Should not match due to case sensitivity

        # Case-insensitive pattern
        pattern_ci = re.compile(r"DEPLOY", re.IGNORECASE)
        match = check_pattern_match("deploy", pattern_ci)

        assert match is not None  # Should match

        # Multiline pattern
        pattern_ml = re.compile(r"^prod$", re.MULTILINE)
        match = check_pattern_match("staging\nprod\ndev", pattern_ml)

        assert match is None  # Pattern expects exact match from start

    def test_parse_mentions_for_username_default(self):
        event = sansio.Event(
            {"comment": {"body": "@bot help @otherbot test"}},
            event="issue_comment",
            delivery_id="test",
        )

        mentions = parse_mentions_for_username(event, None)  # Uses default "bot"

        assert len(mentions) == 1
        assert mentions[0].username == "bot"
        assert mentions[0].text == "help @otherbot test"

    def test_parse_mentions_for_username_specific(self):
        event = sansio.Event(
            {"comment": {"body": "@bot help @deploy-bot test @test-bot check"}},
            event="issue_comment",
            delivery_id="test",
        )

        mentions = parse_mentions_for_username(event, "deploy-bot")

        assert len(mentions) == 1
        assert mentions[0].username == "deploy-bot"
        assert mentions[0].text == "test @test-bot check"

    def test_parse_mentions_for_username_regex(self):
        event = sansio.Event(
            {
                "comment": {
                    "body": "@bot help @deploy-bot test @test-bot check @user ignore"
                }
            },
            event="issue_comment",
            delivery_id="test",
        )

        mentions = parse_mentions_for_username(event, re.compile(r".*-bot"))

        assert len(mentions) == 2
        assert mentions[0].username == "deploy-bot"
        assert mentions[0].text == "test"
        assert mentions[1].username == "test-bot"
        assert mentions[1].text == "check @user ignore"

        assert mentions[0].next_mention is mentions[1]
        assert mentions[1].previous_mention is mentions[0]

    def test_parse_mentions_for_username_all(self):
        event = sansio.Event(
            {"comment": {"body": "@alice review @bob help @charlie test"}},
            event="issue_comment",
            delivery_id="test",
        )

        mentions = parse_mentions_for_username(event, re.compile(r".*"))

        assert len(mentions) == 3
        assert mentions[0].username == "alice"
        assert mentions[0].text == "review"
        assert mentions[1].username == "bob"
        assert mentions[1].text == "help"
        assert mentions[2].username == "charlie"
        assert mentions[2].text == "test"
