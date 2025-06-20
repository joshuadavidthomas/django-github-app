from __future__ import annotations

import re
import time

import pytest
from django.test import override_settings
from django.utils import timezone

from django_github_app.mentions import Comment
from django_github_app.mentions import LineInfo
from django_github_app.mentions import Mention
from django_github_app.mentions import MentionScope
from django_github_app.mentions import RawMention
from django_github_app.mentions import extract_all_mentions
from django_github_app.mentions import extract_mention_text
from django_github_app.mentions import extract_mentions_from_event
from django_github_app.mentions import get_match
from django_github_app.mentions import matches_pattern


@pytest.fixture(autouse=True)
def setup_test_app_name(override_app_settings):
    with override_app_settings(NAME="bot"):
        yield


class TestExtractAllMentions:
    @pytest.mark.parametrize(
        "text,expected_mentions",
        [
            # Valid usernames
            ("@validuser", [("validuser", 0, 10)]),
            ("@Valid-User-123", [("Valid-User-123", 0, 15)]),
            ("@123startswithnumber", [("123startswithnumber", 0, 20)]),
            # Multiple mentions
            (
                "@alice review @bob help @charlie test",
                [("alice", 0, 6), ("bob", 14, 18), ("charlie", 24, 32)],
            ),
            # Invalid patterns - partial extraction
            ("@-invalid", []),  # Can't start with hyphen
            ("@invalid-", [("invalid", 0, 8)]),  # Hyphen at end not included
            ("@in--valid", [("in", 0, 3)]),  # Stops at double hyphen
            # Long username - truncated to 39 chars
            (
                "@toolongusernamethatexceedsthirtyninecharacters",
                [("toolongusernamethatexceedsthirtyninecha", 0, 40)],
            ),
            # Special blocks tested in test_preserves_positions_with_special_blocks
            # Edge cases
            ("@", []),  # Just @ symbol
            ("@@double", []),  # Double @ symbol
            ("email@example.com", []),  # Email (not at start of word)
            ("@123", [("123", 0, 4)]),  # Numbers only
            ("@user_name", [("user", 0, 5)]),  # Underscore stops extraction
            ("test@user", []),  # Not at word boundary
            ("@user@another", [("user", 0, 5)]),  # Second @ not at boundary
        ],
    )
    def test_extract_all_mentions(self, text, expected_mentions):
        mentions = extract_all_mentions(text)

        assert len(mentions) == len(expected_mentions)
        for i, (username, start, end) in enumerate(expected_mentions):
            assert mentions[i].username == username
            assert mentions[i].position == start
            assert mentions[i].end == end

    @pytest.mark.parametrize(
        "text,expected_mentions",
        [
            # Code block with triple backticks
            (
                "Before code\n```\n@codebot ignored\n```\n@realbot after",
                [("realbot", 37, 45)],
            ),
            # Inline code with single backticks
            (
                "Use `@inlinebot command` here, but @realbot works",
                [("realbot", 35, 43)],
            ),
            # Blockquote with >
            (
                "> @quotedbot ignored\n@realbot visible",
                [("realbot", 21, 29)],
            ),
            # Multiple code blocks
            (
                "```\n@bot1\n```\nMiddle @bot2\n```\n@bot3\n```\nEnd @bot4",
                [("bot2", 21, 26), ("bot4", 45, 50)],
            ),
            # Nested backticks in code block
            (
                "```\n`@nestedbot`\n```\n@realbot after",
                [("realbot", 21, 29)],
            ),
            # Multiple inline codes
            (
                "`@bot1` and `@bot2` but @bot3 and @bot4",
                [("bot3", 24, 29), ("bot4", 34, 39)],
            ),
            # Mixed special blocks
            (
                "Start\n```\n@codebot\n```\n`@inline` text\n> @quoted line\n@realbot end",
                [("realbot", 53, 61)],
            ),
            # Empty code block
            (
                "Before\n```\n\n```\n@realbot after",
                [("realbot", 16, 24)],
            ),
            # Code block at start
            (
                "```\n@ignored\n```\n@realbot only",
                [("realbot", 17, 25)],
            ),
            # Multiple blockquotes
            (
                "> @bot1 quoted\n> @bot2 also quoted\n@bot3 not quoted",
                [("bot3", 35, 40)],
            ),
        ],
    )
    def test_preserves_positions_with_special_blocks(self, text, expected_mentions):
        mentions = extract_all_mentions(text)

        assert len(mentions) == len(expected_mentions)
        for i, (username, start, end) in enumerate(expected_mentions):
            assert mentions[i].username == username
            assert mentions[i].position == start
            assert mentions[i].end == end
            # Verify positions are preserved despite replacements
            assert text[mentions[i].position : mentions[i].end] == f"@{username}"


class TestExtractMentionsFromEvent:
    @pytest.mark.parametrize(
        "body,username_pattern,expected",
        [
            # Simple mention with command
            (
                "@mybot help",
                "mybot",
                [{"username": "mybot", "text": "help"}],
            ),
            # Mention without command
            ("@mybot", "mybot", [{"username": "mybot", "text": ""}]),
            # Case insensitive matching - preserves original case
            ("@MyBot help", "mybot", [{"username": "MyBot", "text": "help"}]),
            # Command case preserved
            ("@mybot HELP", "mybot", [{"username": "mybot", "text": "HELP"}]),
            # Mention in middle
            ("Hey @mybot help me", "mybot", [{"username": "mybot", "text": "help me"}]),
            # With punctuation
            ("@mybot help!", "mybot", [{"username": "mybot", "text": "help!"}]),
            # No space after mention
            (
                "@mybot, please help",
                "mybot",
                [{"username": "mybot", "text": ", please help"}],
            ),
            # Multiple spaces before command
            ("@mybot    help", "mybot", [{"username": "mybot", "text": "help"}]),
            # Hyphenated command
            (
                "@mybot async-test",
                "mybot",
                [{"username": "mybot", "text": "async-test"}],
            ),
            # Special character command
            ("@mybot ?", "mybot", [{"username": "mybot", "text": "?"}]),
            # Hyphenated username matches pattern
            ("@my-bot help", "my-bot", [{"username": "my-bot", "text": "help"}]),
            # Username with underscore - doesn't match pattern
            ("@my_bot help", "my_bot", []),
            # Empty text
            ("", "mybot", []),
        ],
    )
    def test_mention_extraction_scenarios(
        self, body, username_pattern, expected, create_event
    ):
        event = create_event("issue_comment", comment={"body": body} if body else {})

        mentions = extract_mentions_from_event(event, username_pattern)

        assert len(mentions) == len(expected)
        for i, exp in enumerate(expected):
            assert mentions[i].username == exp["username"]
            assert mentions[i].text == exp["text"]

    @pytest.mark.parametrize(
        "body,bot_pattern,expected",
        [
            # Multiple mentions of same bot
            (
                "@mybot help and then @mybot deploy",
                "mybot",
                [{"text": "help and then"}, {"text": "deploy"}],
            ),
            # Ignore other mentions
            (
                "@otheruser help @mybot deploy @someone else",
                "mybot",
                [{"text": "deploy"}],
            ),
        ],
    )
    def test_multiple_and_filtered_mentions(
        self, body, bot_pattern, expected, create_event
    ):
        event = create_event("issue_comment", comment={"body": body})

        mentions = extract_mentions_from_event(event, bot_pattern)

        assert len(mentions) == len(expected)
        for i, exp in enumerate(expected):
            assert mentions[i].text == exp["text"]

    def test_missing_comment_body(self, create_event):
        event = create_event("issue_comment")

        mentions = extract_mentions_from_event(event, "mybot")

        assert mentions == []

    @pytest.mark.parametrize(
        "body,bot_pattern,expected_mentions",
        [
            # Default pattern (None uses "bot" from test settings)
            ("@bot help @otherbot test", None, [("bot", "help")]),
            # Specific bot name
            (
                "@bot help @deploy-bot test @test-bot check",
                "deploy-bot",
                [("deploy-bot", "test")],
            ),
        ],
    )
    def test_extract_mentions_from_event_patterns(
        self, body, bot_pattern, expected_mentions, create_event
    ):
        event = create_event("issue_comment", comment={"body": body})

        mentions = extract_mentions_from_event(event, bot_pattern)

        assert len(mentions) == len(expected_mentions)
        for i, (username, text) in enumerate(expected_mentions):
            assert mentions[i].username == username
            assert mentions[i].text == text

    def test_mention_linking(self, create_event):
        event = create_event(
            "issue_comment",
            comment={"body": "@bot1 first @bot2 second @bot3 third"},
        )

        mentions = extract_mentions_from_event(event, re.compile(r"bot\d"))

        assert len(mentions) == 3
        # First mention
        assert mentions[0].previous_mention is None
        assert mentions[0].next_mention is mentions[1]
        # Second mention
        assert mentions[1].previous_mention is mentions[0]
        assert mentions[1].next_mention is mentions[2]
        # Third mention
        assert mentions[2].previous_mention is mentions[1]
        assert mentions[2].next_mention is None

    def test_mention_text_extraction_stops_at_next_mention(self, create_event):
        event = create_event(
            "issue_comment",
            comment={"body": "@bot1 first command @bot2 second command @bot3 third"},
        )

        mentions = extract_mentions_from_event(event, re.compile(r"bot[123]"))

        assert len(mentions) == 3
        assert mentions[0].username == "bot1"
        assert mentions[0].text == "first command"
        assert mentions[1].username == "bot2"
        assert mentions[1].text == "second command"
        assert mentions[2].username == "bot3"
        assert mentions[2].text == "third"


class TestMentionScope:
    @pytest.mark.parametrize(
        "event_type,data,expected",
        [
            ("issue_comment", {}, MentionScope.ISSUE),
            (
                "issue_comment",
                {"issue": {"pull_request": {"url": "..."}}},
                MentionScope.PR,
            ),
            ("issue_comment", {"issue": {"pull_request": None}}, MentionScope.ISSUE),
            ("pull_request_review", {}, MentionScope.PR),
            ("pull_request_review_comment", {}, MentionScope.PR),
            ("commit_comment", {}, MentionScope.COMMIT),
            ("unknown_event", {}, None),
        ],
    )
    def test_from_event(self, event_type, data, expected, create_event):
        event = create_event(event_type=event_type, **data)

        assert MentionScope.from_event(event) == expected


class TestComment:
    @pytest.mark.parametrize(
        "event_type",
        [
            "issue_comment",
            "pull_request_review_comment",
            "pull_request_review",
            "commit_comment",
        ],
    )
    def test_from_event(self, event_type, create_event):
        event = create_event(event_type)

        comment = Comment.from_event(event)

        assert isinstance(comment.body, str)
        assert isinstance(comment.author, str)
        assert comment.created_at is not None
        assert isinstance(comment.url, str)
        assert comment.mentions == []
        assert isinstance(comment.line_count, int)

    def test_from_event_missing_fields(self, create_event):
        event = create_event(
            "issue_comment",
            comment={
                "user": {},  # Empty with no login to test fallback
            },
            sender={"login": "fallback-user"},
        )

        comment = Comment.from_event(event)

        assert comment.author == "fallback-user"
        assert comment.url == ""
        # created_at should be roughly now
        assert (timezone.now() - comment.created_at).total_seconds() < 5

    def test_from_event_invalid_event_type(self, create_event):
        event = create_event("push", some_data="value")

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

    @pytest.mark.parametrize(
        "USE_TZ,created_at,expected",
        [
            (True, "2024-01-01T12:00:00Z", "2024-01-01T12:00:00+00:00"),
            (False, "2024-01-01T12:00:00Z", "2024-01-01T12:00:00"),
        ],
    )
    def test_from_event_timezone_handling(
        self, USE_TZ, created_at, expected, create_event
    ):
        event = create_event(
            "issue_comment",
            comment={"created_at": created_at},
        )

        with override_settings(USE_TZ=USE_TZ, TIME_ZONE="UTC"):
            comment = Comment.from_event(event)

        assert comment.created_at.isoformat() == expected


class TestGetMatch:
    @pytest.mark.parametrize(
        "text,pattern,should_match,expected",
        [
            # Literal string matching
            ("deploy production", "deploy", True, "deploy"),
            # Case insensitive - matches but preserves original case
            ("DEPLOY production", "deploy", True, "DEPLOY"),
            # No match
            ("help me", "deploy", False, None),
            # Must start with pattern
            ("please deploy", "deploy", False, None),
        ],
    )
    def test_get_match_literal_string(self, text, pattern, should_match, expected):
        match = get_match(text, pattern)

        if should_match:
            assert match is not None
            assert match.group(0) == expected
        else:
            assert match is None

    @pytest.mark.parametrize(
        "text,pattern,expected_groups",
        [
            # Simple regex with capture group
            (
                "deploy prod",
                re.compile(r"deploy (prod|staging)"),
                {0: "deploy prod", 1: "prod"},
            ),
            # Named groups
            (
                "deploy-prod",
                re.compile(r"deploy-(?P<env>prod|staging|dev)"),
                {0: "deploy-prod", "env": "prod"},
            ),
            # Question mark pattern
            (
                "can you help?",
                re.compile(r".*\?$"),
                {0: "can you help?"},
            ),
            # No match
            (
                "deploy test",
                re.compile(r"deploy (prod|staging)"),
                None,
            ),
        ],
    )
    def test_get_match_regex(self, text, pattern, expected_groups):
        match = get_match(text, pattern)

        if expected_groups is None:
            assert match is None
        else:
            assert match is not None
            for group_key, expected_value in expected_groups.items():
                assert match.group(group_key) == expected_value

    def test_get_match_none(self):
        match = get_match("any text", None)

        assert match is not None
        assert match.group(0) == "any text"

    @pytest.mark.parametrize(
        "text,pattern,should_match",
        [
            # Invalid regex treated as literal - doesn't start with [invalid
            ("test [invalid", "[invalid", False),
            # Invalid regex treated as literal - starts with [invalid
            ("[invalid regex", "[invalid", True),
        ],
    )
    def test_get_match_invalid_regex(self, text, pattern, should_match):
        match = get_match(text, pattern)

        if should_match:
            assert match is not None
        else:
            assert match is None

    @pytest.mark.parametrize(
        "text,pattern,should_match",
        [
            # Case-sensitive pattern
            ("deploy", re.compile(r"DEPLOY", re.MULTILINE), False),
            # Case-insensitive pattern
            ("deploy", re.compile(r"DEPLOY", re.IGNORECASE), True),
            # Multiline pattern - expects match from start of text
            ("staging\nprod\ndev", re.compile(r"^prod$", re.MULTILINE), False),
        ],
    )
    def test_get_match_flag_preservation(self, text, pattern, should_match):
        match = get_match(text, pattern)

        if should_match:
            assert match is not None
        else:
            assert match is None


class TestReDoSProtection:
    def test_redos_vulnerability(self, create_event):
        # Create a malicious comment that would cause potentially cause ReDoS
        # Pattern: (bot|ai|assistant)+ matching "botbotbot...x"
        malicious_username = "bot" * 20 + "x"
        event = create_event(
            "issue_comment", comment={"body": f"@{malicious_username} hello"}
        )

        pattern = re.compile(r"(bot|ai|assistant)+")

        start_time = time.time()
        mentions = extract_mentions_from_event(event, pattern)
        execution_time = time.time() - start_time

        assert execution_time < 0.1
        # The username gets truncated at 39 chars, and the 'x' is left out
        # So it will match the pattern, but the important thing is it completes quickly
        assert len(mentions) == 1
        assert mentions[0].username == "botbotbotbotbotbotbotbotbotbotbotbotbot"

    def test_nested_quantifier_pattern(self, create_event):
        event = create_event(
            "issue_comment", comment={"body": "@deploy-bot-bot-bot test command"}
        )

        # This type of pattern could cause issues: (word)+
        pattern = re.compile(r"(deploy|bot)+")

        start_time = time.time()
        mentions = extract_mentions_from_event(event, pattern)
        execution_time = time.time() - start_time

        assert execution_time < 0.1
        # Username contains hyphens, so it won't match this pattern
        assert len(mentions) == 0

    def test_alternation_with_quantifier(self, create_event):
        event = create_event(
            "issue_comment", comment={"body": "@mybot123bot456bot789 deploy"}
        )

        # Pattern like (a|b)* that could be dangerous
        pattern = re.compile(r"(my|bot|[0-9])+")

        start_time = time.time()
        mentions = extract_mentions_from_event(event, pattern)
        execution_time = time.time() - start_time

        assert execution_time < 0.1
        # Should match safely
        assert len(mentions) == 1
        assert mentions[0].username == "mybot123bot456bot789"

    def test_complex_regex_patterns_handled_safely(self, create_event):
        event = create_event(
            "issue_comment",
            comment={
                "body": "@test @test-bot @test-bot-123 @testbotbotbot @verylongusername123456789"
            },
        )

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

            assert execution_time < 0.1

    def test_performance_with_many_mentions(self, create_event):
        usernames = [f"@user{i}" for i in range(100)]
        comment_body = " ".join(usernames) + " Please review all"
        event = create_event("issue_comment", comment={"body": comment_body})

        pattern = re.compile(r"user\d+")

        start_time = time.time()
        mentions = extract_mentions_from_event(event, pattern)
        execution_time = time.time() - start_time

        assert execution_time < 0.5
        assert len(mentions) == 100
        for i, mention in enumerate(mentions):
            assert mention.username == f"user{i}"


class TestLineInfo:
    @pytest.mark.parametrize(
        "comment,position,expected_lineno,expected_text",
        [
            # Single line mentions
            ("@user hello", 0, 1, "@user hello"),
            ("Hey @user how are you?", 4, 1, "Hey @user how are you?"),
            ("Thanks @user", 7, 1, "Thanks @user"),
            # Multi-line mentions
            (
                "@user please review\nthis pull request\nthanks!",
                0,
                1,
                "@user please review",
            ),
            ("Hello there\n@user can you help?\nThanks!", 12, 2, "@user can you help?"),
            ("First line\nSecond line\nThanks @user", 31, 3, "Thanks @user"),
            # Empty and edge cases
            ("", 0, 1, ""),
            (
                "Simple comment with @user mention",
                20,
                1,
                "Simple comment with @user mention",
            ),
            # Blank lines
            (
                "First line\n\n@user on third line\n\nFifth line",
                12,
                3,
                "@user on third line",
            ),
            ("\n\n\n@user appears here", 3, 4, "@user appears here"),
            # Unicode/emoji
            (
                "First line 👋\n@user こんにちは 🎉\nThird line",
                14,
                2,
                "@user こんにちは 🎉",
            ),
        ],
    )
    def test_for_mention_in_comment(
        self, comment, position, expected_lineno, expected_text
    ):
        line_info = LineInfo.for_mention_in_comment(comment, position)

        assert line_info.lineno == expected_lineno
        assert line_info.text == expected_text

    @pytest.mark.parametrize(
        "comment,position,expected_lineno,expected_text",
        [
            # Trailing newlines should be stripped from line text
            ("Hey @user\n", 4, 1, "Hey @user"),
            # Position beyond comment length
            ("Short", 100, 1, "Short"),
            # Unix-style line endings
            ("Line 1\n@user line 2", 7, 2, "@user line 2"),
            # Windows-style line endings (\r\n handled as single separator)
            ("Line 1\r\n@user line 2", 8, 2, "@user line 2"),
        ],
    )
    def test_edge_cases(self, comment, position, expected_lineno, expected_text):
        line_info = LineInfo.for_mention_in_comment(comment, position)

        assert line_info.lineno == expected_lineno
        assert line_info.text == expected_text

    @pytest.mark.parametrize(
        "comment,position,expected_lineno",
        [
            ("Hey @alice and @bob, please review", 4, 1),
            ("Hey @alice and @bob, please review", 15, 1),
        ],
    )
    def test_multiple_mentions_same_line(self, comment, position, expected_lineno):
        line_info = LineInfo.for_mention_in_comment(comment, position)

        assert line_info.lineno == expected_lineno
        assert line_info.text == comment


class TestMatchesPattern:
    @pytest.mark.parametrize(
        "text,pattern,expected",
        [
            # String patterns - exact match (case insensitive)
            ("deploy", "deploy", True),
            ("DEPLOY", "deploy", True),
            ("deploy", "DEPLOY", True),
            ("Deploy", "deploy", True),
            # String patterns - whitespace handling
            ("  deploy  ", "deploy", True),
            ("deploy", "  deploy  ", True),
            ("  deploy  ", "  deploy  ", True),
            # String patterns - no match
            ("deploy prod", "deploy", False),
            ("deployment", "deploy", False),
            ("redeploy", "deploy", False),
            ("help", "deploy", False),
            # Empty strings
            ("", "", True),
            ("deploy", "", False),
            ("", "deploy", False),
            # Special characters in string patterns
            ("deploy-prod", "deploy-prod", True),
            ("deploy_prod", "deploy_prod", True),
            ("deploy.prod", "deploy.prod", True),
        ],
    )
    def test_string_pattern_matching(self, text, pattern, expected):
        assert matches_pattern(text, pattern) == expected

    @pytest.mark.parametrize(
        "text,pattern_str,flags,expected",
        [
            # Basic regex patterns
            ("deploy", r"deploy", 0, True),
            ("deploy prod", r"deploy", 0, False),  # fullmatch requires entire string
            ("deploy", r".*deploy.*", 0, True),
            ("redeploy", r".*deploy.*", 0, True),
            # Case sensitivity with regex - moved to test_pattern_flags_preserved
            # Complex regex patterns
            ("deploy-prod", r"deploy-(prod|staging|dev)", 0, True),
            ("deploy-staging", r"deploy-(prod|staging|dev)", 0, True),
            ("deploy-test", r"deploy-(prod|staging|dev)", 0, False),
            # Anchored patterns (fullmatch behavior)
            ("deploy prod", r"^deploy$", 0, False),
            ("deploy", r"^deploy$", 0, True),
            # Wildcards and quantifiers
            ("deploy", r"dep.*", 0, True),
            ("deployment", r"deploy.*", 0, True),
            ("dep", r"deploy?", 0, False),  # fullmatch requires entire string
            # Character classes
            ("deploy123", r"deploy\d+", 0, True),
            ("deploy-abc", r"deploy\d+", 0, False),
            # Empty pattern
            ("anything", r".*", 0, True),
            ("", r".*", 0, True),
            # Suffix matching (from removed test)
            ("deploy-bot", r".*-bot", 0, True),
            ("test-bot", r".*-bot", 0, True),
            ("user", r".*-bot", 0, False),
            # Prefix with digits (from removed test)
            ("mybot1", r"mybot\d+", 0, True),
            ("mybot2", r"mybot\d+", 0, True),
            ("otherbot", r"mybot\d+", 0, False),
        ],
    )
    def test_regex_pattern_matching(self, text, pattern_str, flags, expected):
        pattern = re.compile(pattern_str, flags)

        assert matches_pattern(text, pattern) == expected

    @pytest.mark.parametrize(
        "text,expected",
        [
            # re.match would return True for these, but fullmatch returns False
            ("deploy prod", False),
            ("deployment", False),
            # Only exact full matches should return True
            ("deploy", True),
        ],
    )
    def test_regex_fullmatch_vs_match_behavior(self, text, expected):
        pattern = re.compile(r"deploy")

        assert matches_pattern(text, pattern) is expected

    @pytest.mark.parametrize(
        "text,pattern_str,flags,expected",
        [
            # Case insensitive pattern
            ("DEPLOY", r"deploy", re.IGNORECASE, True),
            ("Deploy", r"deploy", re.IGNORECASE, True),
            ("deploy", r"deploy", re.IGNORECASE, True),
            # Case sensitive pattern (default)
            ("DEPLOY", r"deploy", 0, False),
            ("Deploy", r"deploy", 0, False),
            ("deploy", r"deploy", 0, True),
            # DOTALL flag allows . to match newlines
            ("line1\nline2", r"line1.*line2", re.DOTALL, True),
            (
                "line1\nline2",
                r"line1.*line2",
                0,
                False,
            ),  # Without DOTALL, . doesn't match \n
            ("line1 line2", r"line1.*line2", 0, True),
        ],
    )
    def test_pattern_flags_preserved(self, text, pattern_str, flags, expected):
        pattern = re.compile(pattern_str, flags)

        assert matches_pattern(text, pattern) == expected


class TestMention:
    @pytest.mark.parametrize(
        "event_type,event_data,username,pattern,scope,expected_count,expected_mentions",
        [
            # Basic mention extraction
            (
                "issue_comment",
                {"comment": {"body": "@bot help"}},
                "bot",
                None,
                None,
                1,
                [{"username": "bot", "text": "help"}],
            ),
            # No mentions in event
            (
                "issue_comment",
                {"comment": {"body": "No mentions here"}},
                None,
                None,
                None,
                0,
                [],
            ),
            # Multiple mentions, filter by username
            (
                "issue_comment",
                {"comment": {"body": "@bot1 help @bot2 deploy @user test"}},
                re.compile(r"bot\d"),
                None,
                None,
                2,
                [
                    {"username": "bot1", "text": "help"},
                    {"username": "bot2", "text": "deploy"},
                ],
            ),
            # Scope filtering - matching scope
            (
                "issue_comment",
                {"comment": {"body": "@bot help"}, "issue": {}},
                "bot",
                None,
                MentionScope.ISSUE,
                1,
                [{"username": "bot", "text": "help"}],
            ),
            # Scope filtering - non-matching scope (PR comment on issue-only scope)
            (
                "issue_comment",
                {"comment": {"body": "@bot help"}, "issue": {"pull_request": {}}},
                "bot",
                None,
                MentionScope.ISSUE,
                0,
                [],
            ),
            # Pattern matching on mention text
            (
                "issue_comment",
                {"comment": {"body": "@bot deploy prod @bot help me"}},
                "bot",
                re.compile(r"deploy.*"),
                None,
                1,
                [{"username": "bot", "text": "deploy prod"}],
            ),
            # String pattern matching (case insensitive)
            (
                "issue_comment",
                {"comment": {"body": "@bot DEPLOY @bot help"}},
                "bot",
                "deploy",
                None,
                1,
                [{"username": "bot", "text": "DEPLOY"}],
            ),
            # No username filter defaults to app name (bot)
            (
                "issue_comment",
                {"comment": {"body": "@alice review @bot help"}},
                None,
                None,
                None,
                1,
                [{"username": "bot", "text": "help"}],
            ),
            # Get all mentions with wildcard regex pattern
            (
                "issue_comment",
                {"comment": {"body": "@alice review @bob help"}},
                re.compile(r".*"),
                None,
                None,
                2,
                [
                    {"username": "alice", "text": "review"},
                    {"username": "bob", "text": "help"},
                ],
            ),
            # PR review comment
            (
                "pull_request_review_comment",
                {"comment": {"body": "@reviewer please check"}},
                "reviewer",
                None,
                MentionScope.PR,
                1,
                [{"username": "reviewer", "text": "please check"}],
            ),
            # Commit comment
            (
                "commit_comment",
                {"comment": {"body": "@bot test this commit"}},
                "bot",
                None,
                MentionScope.COMMIT,
                1,
                [{"username": "bot", "text": "test this commit"}],
            ),
            # Complex filtering: username + pattern + scope
            (
                "issue_comment",
                {
                    "comment": {
                        "body": "@mybot deploy staging @otherbot deploy prod @mybot help"
                    }
                },
                "mybot",
                re.compile(r"deploy\s+(staging|prod)"),
                None,
                1,
                [{"username": "mybot", "text": "deploy staging"}],
            ),
            # Empty comment body
            (
                "issue_comment",
                {"comment": {"body": ""}},
                None,
                None,
                None,
                0,
                [],
            ),
            # Mentions in code blocks (should be ignored)
            (
                "issue_comment",
                {"comment": {"body": "```\n@bot deploy\n```\n@bot help"}},
                "bot",
                None,
                None,
                1,
                [{"username": "bot", "text": "help"}],
            ),
        ],
    )
    def test_from_event(
        self,
        create_event,
        event_type,
        event_data,
        username,
        pattern,
        scope,
        expected_count,
        expected_mentions,
    ):
        event = create_event(event_type, **event_data)

        mentions = list(
            Mention.from_event(event, username=username, pattern=pattern, scope=scope)
        )

        assert len(mentions) == expected_count
        for mention, expected in zip(mentions, expected_mentions, strict=False):
            assert isinstance(mention, Mention)
            assert mention.mention.username == expected["username"]
            assert mention.mention.text == expected["text"]
            assert mention.comment.body == event_data["comment"]["body"]
            assert mention.scope == MentionScope.from_event(event)

            # Verify match object is set when pattern is provided
            if pattern is not None:
                assert mention.mention.match is not None

    @pytest.mark.parametrize(
        "body,username,pattern,expected_matches",
        [
            # Pattern groups are accessible via match object
            (
                "@bot deploy prod to server1",
                "bot",
                re.compile(r"deploy\s+(\w+)\s+to\s+(\w+)"),
                [("prod", "server1")],
            ),
            # Named groups
            (
                "@bot deploy staging",
                "bot",
                re.compile(r"deploy\s+(?P<env>prod|staging|dev)"),
                [{"env": "staging"}],
            ),
        ],
    )
    def test_from_event_pattern_groups(
        self, create_event, body, username, pattern, expected_matches
    ):
        event = create_event("issue_comment", comment={"body": body})

        mentions = list(Mention.from_event(event, username=username, pattern=pattern))

        assert len(mentions) == len(expected_matches)
        for mention, expected in zip(mentions, expected_matches, strict=False):
            assert mention.mention.match is not None
            if isinstance(expected, tuple):
                assert mention.mention.match.groups() == expected
            elif isinstance(expected, dict):
                assert mention.mention.match.groupdict() == expected


class TestExtractMentionText:
    @pytest.fixture
    def create_raw_mention(self):
        def _create(username: str, position: int, end: int) -> RawMention:
            # Create a dummy match object - extract_mention_text doesn't use it
            dummy_text = f"@{username}"
            match = re.match(r"@(\w+)", dummy_text)
            assert match is not None  # For type checker
            return RawMention(
                match=match, username=username, position=position, end=end
            )

        return _create

    @pytest.mark.parametrize(
        "body,all_mentions_data,mention_end,expected_text",
        [
            # Basic case: text after mention until next mention
            (
                "@user1 hello world @user2 goodbye",
                [("user1", 0, 6), ("user2", 19, 25)],
                6,
                "hello world",
            ),
            # No text after mention (next mention immediately follows)
            (
                "@user1@user2 hello",
                [("user1", 0, 6), ("user2", 6, 12)],
                6,
                "",
            ),
            # Empty text between mentions (whitespace only)
            (
                "@user1   @user2",
                [("user1", 0, 6), ("user2", 9, 15)],
                6,
                "",
            ),
            # Single mention with text
            (
                "@user hello world",
                [("user", 0, 5)],
                5,
                "hello world",
            ),
            # Mention at end of string
            (
                "Hello @user",
                [("user", 6, 11)],
                11,
                "",
            ),
            # Multiple spaces and newlines (should be stripped)
            (
                "@user1  \n\n  hello world  \n  @user2",
                [("user1", 0, 6), ("user2", 28, 34)],
                6,
                "hello world",
            ),
            # Text with special characters
            (
                "@bot deploy-prod --force @admin",
                [("bot", 0, 4), ("admin", 25, 31)],
                4,
                "deploy-prod --force",
            ),
            # Unicode text
            (
                "@user こんにちは 🎉 @other",
                [("user", 0, 5), ("other", 14, 20)],
                5,
                "こんにちは 🎉",
            ),
            # Empty body
            (
                "",
                [],
                0,
                "",
            ),
            # Complex multi-line text
            (
                "@user1 Line 1\nLine 2\nLine 3 @user2 End",
                [("user1", 0, 6), ("user2", 28, 34)],
                6,
                "Line 1\nLine 2\nLine 3",
            ),
            # Trailing whitespace should be stripped
            (
                "@user text with trailing spaces    ",
                [("user", 0, 5)],
                5,
                "text with trailing spaces",
            ),
        ],
    )
    def test_extract_mention_text(
        self, create_raw_mention, body, all_mentions_data, mention_end, expected_text
    ):
        all_mentions = [
            create_raw_mention(username, pos, end)
            for username, pos, end in all_mentions_data
        ]

        result = extract_mention_text(body, 0, all_mentions, mention_end)

        assert result == expected_text

    @pytest.mark.parametrize(
        "body,current_index,all_mentions_data,mention_end,expected_text",
        [
            # Last mention: text until end of string
            (
                "@user1 hello @user2 goodbye world",
                1,
                [("user1", 0, 6), ("user2", 13, 19)],
                19,
                "goodbye world",
            ),
            # Current index is not first mention
            (
                "@alice intro @bob middle text @charlie end",
                1,  # Looking at @bob
                [
                    ("alice", 0, 6),
                    ("bob", 13, 17),
                    ("charlie", 30, 38),
                ],
                17,
                "middle text",
            ),
            # Multiple mentions with different current indices
            (
                "@a first @b second @c third @d fourth",
                2,  # Looking at @c
                [
                    ("a", 0, 2),
                    ("b", 9, 11),
                    ("c", 19, 21),
                    ("d", 28, 30),
                ],
                21,
                "third",
            ),
        ],
    )
    def test_extract_mention_text_with_different_current_index(
        self,
        create_raw_mention,
        body,
        current_index,
        all_mentions_data,
        mention_end,
        expected_text,
    ):
        all_mentions = [
            create_raw_mention(username, pos, end)
            for username, pos, end in all_mentions_data
        ]

        result = extract_mention_text(body, current_index, all_mentions, mention_end)

        assert result == expected_text

    @pytest.mark.parametrize(
        "current_index,expected_text",
        [
            # Last mention - should get text until end
            (1, "world"),
            # Out of bounds current_index (should still work)
            (10, "world"),
        ],
    )
    def test_extract_mention_text_with_invalid_indices(
        self, create_raw_mention, current_index, expected_text
    ):
        all_mentions = [
            create_raw_mention("user1", 0, 6),
            create_raw_mention("user2", 13, 19),
        ]

        result = extract_mention_text(
            "@user1 hello @user2 world", current_index, all_mentions, 19
        )

        assert result == expected_text
