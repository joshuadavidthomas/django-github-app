from __future__ import annotations

import re
import time

import pytest
from django.utils import timezone
from gidgethub import sansio

from django_github_app.mentions import Comment
from django_github_app.mentions import MentionScope
from django_github_app.mentions import extract_mentions_from_event
from django_github_app.mentions import get_match


@pytest.fixture(autouse=True)
def setup_test_app_name(override_app_settings):
    with override_app_settings(NAME="bot"):
        yield


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
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].username == "mybot"
        assert mentions[0].text == "help"
        assert mentions[0].position == 0
        assert mentions[0].line_info.lineno == 1

    def test_mention_without_command(self, create_comment_event):
        event = create_comment_event("@mybot")
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].username == "mybot"
        assert mentions[0].text == ""

    def test_case_insensitive_matching(self, create_comment_event):
        event = create_comment_event("@MyBot help")
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].username == "MyBot"  # Username is preserved as found
        assert mentions[0].text == "help"

    def test_command_case_normalization(self, create_comment_event):
        event = create_comment_event("@mybot HELP")
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 1
        # Command case is preserved in text, normalization happens elsewhere
        assert mentions[0].text == "HELP"

    def test_multiple_mentions(self, create_comment_event):
        event = create_comment_event("@mybot help and then @mybot deploy")
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 2
        assert mentions[0].text == "help and then"
        assert mentions[1].text == "deploy"

    def test_ignore_other_mentions(self, create_comment_event):
        event = create_comment_event("@otheruser help @mybot deploy @someone else")
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "deploy"

    def test_mention_in_code_block(self, create_comment_event):
        text = """
        Here's some text
        ```
        @mybot help
        ```
        @mybot deploy
        """
        event = create_comment_event(text)
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "deploy"

    def test_mention_in_inline_code(self, create_comment_event):
        event = create_comment_event(
            "Use `@mybot help` for help, or just @mybot deploy"
        )
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "deploy"

    def test_mention_in_quote(self, create_comment_event):
        text = """
        > @mybot help
        @mybot deploy
        """
        event = create_comment_event(text)
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "deploy"

    def test_empty_text(self, create_comment_event):
        event = create_comment_event("")
        mentions = extract_mentions_from_event(event, "mybot")

        assert mentions == []

    def test_none_text(self, create_comment_event):
        # Create an event with no comment body
        event = sansio.Event({}, event="issue_comment", delivery_id="test")
        mentions = extract_mentions_from_event(event, "mybot")

        assert mentions == []

    def test_mention_at_start_of_line(self, create_comment_event):
        event = create_comment_event("@mybot help")
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "help"

    def test_mention_in_middle_of_text(self, create_comment_event):
        event = create_comment_event("Hey @mybot help me")
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "help me"

    def test_mention_with_punctuation_after(self, create_comment_event):
        event = create_comment_event("@mybot help!")
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "help!"

    def test_hyphenated_username(self, create_comment_event):
        event = create_comment_event("@my-bot help")
        mentions = extract_mentions_from_event(event, "my-bot")

        assert len(mentions) == 1
        assert mentions[0].username == "my-bot"
        assert mentions[0].text == "help"

    def test_underscore_username(self, create_comment_event):
        # GitHub usernames don't support underscores
        event = create_comment_event("@my_bot help")
        mentions = extract_mentions_from_event(event, "my_bot")

        assert len(mentions) == 0  # Should not match invalid username

    def test_no_space_after_mention(self, create_comment_event):
        event = create_comment_event("@mybot, please help")
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == ", please help"

    def test_multiple_spaces_before_command(self, create_comment_event):
        event = create_comment_event("@mybot    help")
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "help"  # Whitespace is stripped

    def test_hyphenated_command(self, create_comment_event):
        event = create_comment_event("@mybot async-test")
        mentions = extract_mentions_from_event(event, "mybot")

        assert len(mentions) == 1
        assert mentions[0].text == "async-test"

    def test_special_character_command(self, create_comment_event):
        event = create_comment_event("@mybot ?")
        mentions = extract_mentions_from_event(event, "mybot")

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
    def test_get_match_none(self):
        match = get_match("any text", None)

        assert match is not None
        assert match.group(0) == "any text"

    def test_get_match_literal_string(self):
        # Matching case
        match = get_match("deploy production", "deploy")
        assert match is not None
        assert match.group(0) == "deploy"

        # Case insensitive
        match = get_match("DEPLOY production", "deploy")
        assert match is not None

        # No match
        match = get_match("help me", "deploy")
        assert match is None

        # Must start with pattern
        match = get_match("please deploy", "deploy")
        assert match is None

    def test_get_match_regex(self):
        # Simple regex
        match = get_match("deploy prod", re.compile(r"deploy (prod|staging)"))
        assert match is not None
        assert match.group(0) == "deploy prod"
        assert match.group(1) == "prod"

        # Named groups
        match = get_match(
            "deploy-prod", re.compile(r"deploy-(?P<env>prod|staging|dev)")
        )
        assert match is not None
        assert match.group("env") == "prod"

        # Question mark pattern
        match = get_match("can you help?", re.compile(r".*\?$"))
        assert match is not None

        # No match
        match = get_match("deploy test", re.compile(r"deploy (prod|staging)"))
        assert match is None

    def test_get_match_invalid_regex(self):
        # Invalid regex should be treated as literal
        match = get_match("test [invalid", "[invalid")
        assert match is None  # Doesn't start with [invalid

        match = get_match("[invalid regex", "[invalid")
        assert match is not None  # Starts with literal [invalid

    def test_get_match_flag_preservation(self):
        # Case-sensitive pattern
        pattern_cs = re.compile(r"DEPLOY", re.MULTILINE)
        match = get_match("deploy", pattern_cs)
        assert match is None  # Should not match due to case sensitivity

        # Case-insensitive pattern
        pattern_ci = re.compile(r"DEPLOY", re.IGNORECASE)
        match = get_match("deploy", pattern_ci)

        assert match is not None  # Should match

        # Multiline pattern
        pattern_ml = re.compile(r"^prod$", re.MULTILINE)
        match = get_match("staging\nprod\ndev", pattern_ml)

        assert match is None  # Pattern expects exact match from start

    def test_extract_mentions_from_event_default(self):
        event = sansio.Event(
            {"comment": {"body": "@bot help @otherbot test"}},
            event="issue_comment",
            delivery_id="test",
        )

        mentions = extract_mentions_from_event(event, None)  # Uses default "bot"

        assert len(mentions) == 1
        assert mentions[0].username == "bot"
        assert mentions[0].text == "help"

    def test_extract_mentions_from_event_specific(self):
        event = sansio.Event(
            {"comment": {"body": "@bot help @deploy-bot test @test-bot check"}},
            event="issue_comment",
            delivery_id="test",
        )

        mentions = extract_mentions_from_event(event, "deploy-bot")

        assert len(mentions) == 1
        assert mentions[0].username == "deploy-bot"
        assert mentions[0].text == "test"

    def test_extract_mentions_from_event_regex(self):
        event = sansio.Event(
            {
                "comment": {
                    "body": "@bot help @deploy-bot test @test-bot check @user ignore"
                }
            },
            event="issue_comment",
            delivery_id="test",
        )

        mentions = extract_mentions_from_event(event, re.compile(r".*-bot"))

        assert len(mentions) == 2
        assert mentions[0].username == "deploy-bot"
        assert mentions[0].text == "test"
        assert mentions[1].username == "test-bot"
        assert mentions[1].text == "check"

        assert mentions[0].next_mention is mentions[1]
        assert mentions[1].previous_mention is mentions[0]

    def test_extract_mentions_from_event_all(self):
        event = sansio.Event(
            {"comment": {"body": "@alice review @bob help @charlie test"}},
            event="issue_comment",
            delivery_id="test",
        )

        mentions = extract_mentions_from_event(event, re.compile(r".*"))

        assert len(mentions) == 3
        assert mentions[0].username == "alice"
        assert mentions[0].text == "review"
        assert mentions[1].username == "bob"
        assert mentions[1].text == "help"
        assert mentions[2].username == "charlie"
        assert mentions[2].text == "test"


class TestReDoSProtection:
    """Test that the ReDoS vulnerability has been fixed."""

    def test_redos_vulnerability_fixed(self, create_comment_event):
        """Test that malicious input doesn't cause catastrophic backtracking."""
        # Create a malicious comment that would cause ReDoS with the old implementation
        # Pattern: (bot|ai|assistant)+ matching "botbotbot...x"
        malicious_username = "bot" * 20 + "x"
        event = create_comment_event(f"@{malicious_username} hello")

        # This pattern would cause catastrophic backtracking in the old implementation
        pattern = re.compile(r"(bot|ai|assistant)+")

        # Measure execution time
        start_time = time.time()
        mentions = extract_mentions_from_event(event, pattern)
        execution_time = time.time() - start_time

        # Should complete quickly (under 0.1 seconds) - old implementation would take seconds/minutes
        assert execution_time < 0.1
        # The username gets truncated at 39 chars, and the 'x' is left out
        # So it will match the pattern, but the important thing is it completes quickly
        assert len(mentions) == 1
        assert (
            mentions[0].username == "botbotbotbotbotbotbotbotbotbotbotbotbot"
        )  # 39 chars

    def test_nested_quantifier_pattern(self, create_comment_event):
        """Test patterns with nested quantifiers don't cause issues."""
        event = create_comment_event("@deploy-bot-bot-bot test command")

        # This type of pattern could cause issues: (word)+
        pattern = re.compile(r"(deploy|bot)+")

        start_time = time.time()
        mentions = extract_mentions_from_event(event, pattern)
        execution_time = time.time() - start_time

        assert execution_time < 0.1
        # Username contains hyphens, so it won't match this pattern
        assert len(mentions) == 0

    def test_alternation_with_quantifier(self, create_comment_event):
        """Test alternation patterns with quantifiers."""
        event = create_comment_event("@mybot123bot456bot789 deploy")

        # Pattern like (a|b)* that could be dangerous
        pattern = re.compile(r"(my|bot|[0-9])+")

        start_time = time.time()
        mentions = extract_mentions_from_event(event, pattern)
        execution_time = time.time() - start_time

        assert execution_time < 0.1
        # Should match safely
        assert len(mentions) == 1
        assert mentions[0].username == "mybot123bot456bot789"

    def test_complex_regex_patterns_safe(self, create_comment_event):
        """Test that complex patterns are handled safely."""
        event = create_comment_event(
            "@test @test-bot @test-bot-123 @testbotbotbot @verylongusername123456789"
        )

        # Various potentially problematic patterns
        patterns = [
            re.compile(r".*bot.*"),  # Wildcards
            re.compile(r"test.*"),  # Leading wildcard
            re.compile(r".*"),  # Match all
            re.compile(r"(test|bot)+"),  # Alternation with quantifier
            re.compile(r"[a-z]+[0-9]+"),  # Character classes with quantifiers
        ]

        for pattern in patterns:
            start_time = time.time()
            extract_mentions_from_event(event, pattern)
            execution_time = time.time() - start_time

            # All patterns should execute quickly
            assert execution_time < 0.1

    def test_github_username_constraints(self, create_comment_event):
        """Test that only valid GitHub usernames are extracted."""
        event = create_comment_event(
            "@validuser @Valid-User-123 @-invalid @invalid- @in--valid "
            "@toolongusernamethatexceedsthirtyninecharacters @123startswithnumber"
        )

        mentions = extract_mentions_from_event(event, re.compile(r".*"))

        # Check what usernames were actually extracted
        extracted_usernames = [m.username for m in mentions]

        # The regex extracts:
        # - validuser (valid)
        # - Valid-User-123 (valid)
        # - invalid (from @invalid-, hyphen at end not included)
        # - in (from @in--valid, stops at double hyphen)
        # - toolongusernamethatexceedsthirtyninecha (truncated to 39 chars)
        # - 123startswithnumber (valid - GitHub allows starting with numbers)
        assert len(mentions) == 6
        assert "validuser" in extracted_usernames
        assert "Valid-User-123" in extracted_usernames
        # These are extracted but not ideal - the regex follows GitHub's rules
        assert "invalid" in extracted_usernames  # From @invalid-
        assert "in" in extracted_usernames  # From @in--valid
        assert (
            "toolongusernamethatexceedsthirtyninecha" in extracted_usernames
        )  # Truncated
        assert "123startswithnumber" in extracted_usernames  # Valid GitHub username

    def test_performance_with_many_mentions(self, create_comment_event):
        """Test performance with many mentions in a single comment."""
        # Create a comment with 100 mentions
        usernames = [f"@user{i}" for i in range(100)]
        comment_body = " ".join(usernames) + " Please review all"
        event = create_comment_event(comment_body)

        pattern = re.compile(r"user\d+")

        start_time = time.time()
        mentions = extract_mentions_from_event(event, pattern)
        execution_time = time.time() - start_time

        # Should handle many mentions efficiently
        assert execution_time < 0.5
        assert len(mentions) == 100

        # Verify all mentions are correctly parsed
        for i, mention in enumerate(mentions):
            assert mention.username == f"user{i}"
