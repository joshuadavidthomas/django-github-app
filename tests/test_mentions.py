from __future__ import annotations

import re
import time

import pytest

from django_github_app.mentions import LineInfo
from django_github_app.mentions import Mention
from django_github_app.mentions import MentionScope
from django_github_app.mentions import extract_all_mentions
from django_github_app.mentions import extract_mentions_from_event
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
        "body,username,expected",
        [
            # Simple mention with command
            (
                "@mybot help",
                "mybot",
                [{"username": "mybot"}],
            ),
            # Mention without command
            ("@mybot", "mybot", [{"username": "mybot"}]),
            # Case insensitive matching - preserves original case
            ("@MyBot help", "mybot", [{"username": "MyBot"}]),
            # Command case preserved
            ("@mybot HELP", "mybot", [{"username": "mybot"}]),
            # Mention in middle
            ("Hey @mybot help me", "mybot", [{"username": "mybot"}]),
            # With punctuation
            ("@mybot help!", "mybot", [{"username": "mybot"}]),
            # No space after mention
            (
                "@mybot, please help",
                "mybot",
                [{"username": "mybot"}],
            ),
            # Multiple spaces before command
            ("@mybot    help", "mybot", [{"username": "mybot"}]),
            # Hyphenated command
            (
                "@mybot async-test",
                "mybot",
                [{"username": "mybot"}],
            ),
            # Special character command
            ("@mybot ?", "mybot", [{"username": "mybot"}]),
            # Hyphenated username matches pattern
            ("@my-bot help", "my-bot", [{"username": "my-bot"}]),
            # Username with underscore - doesn't match pattern
            ("@my_bot help", "my_bot", []),
            # Empty text
            ("", "mybot", []),
        ],
    )
    def test_mention_extraction_scenarios(self, body, username, expected, create_event):
        event = create_event("issue_comment", comment={"body": body} if body else {})

        mentions = extract_mentions_from_event(event, username)

        assert len(mentions) == len(expected)
        for i, exp in enumerate(expected):
            assert mentions[i].username == exp["username"]

    @pytest.mark.parametrize(
        "body,bot_pattern,expected_mentions",
        [
            # Multiple mentions of same bot
            (
                "@mybot help and then @mybot deploy",
                "mybot",
                ["mybot", "mybot"],
            ),
            # Filter specific mentions, ignore others
            (
                "@otheruser help @mybot deploy @someone else",
                "mybot",
                ["mybot"],
            ),
            # Default pattern (None matches all mentions)
            ("@bot help @otherbot test", None, ["bot", "otherbot"]),
            # Specific bot name pattern
            (
                "@bot help @deploy-bot test @test-bot check",
                "deploy-bot",
                ["deploy-bot"],
            ),
        ],
    )
    def test_mention_filtering_and_patterns(
        self, body, bot_pattern, expected_mentions, create_event
    ):
        event = create_event("issue_comment", comment={"body": body})

        mentions = extract_mentions_from_event(event, bot_pattern)

        assert len(mentions) == len(expected_mentions)
        for i, username in enumerate(expected_mentions):
            assert mentions[i].username == username

    def test_missing_comment_body(self, create_event):
        event = create_event("issue_comment")

        mentions = extract_mentions_from_event(event, "mybot")

        assert mentions == []

    def test_mention_linking(self, create_event):
        event = create_event(
            "issue_comment",
            comment={"body": "@bot1 first @bot2 second @bot3 third"},
        )

        mentions = extract_mentions_from_event(event, re.compile(r"bot\d"))

        assert len(mentions) == 3

        first = mentions[0]
        second = mentions[1]
        third = mentions[2]

        assert first.previous_mention is None
        assert first.next_mention is second

        assert second.previous_mention is first
        assert second.next_mention is third

        assert third.previous_mention is second
        assert third.next_mention is None


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
        "event_type,event_data,username,expected_count,expected_mentions",
        [
            # Basic mention extraction
            (
                "issue_comment",
                {"comment": {"body": "@bot help"}},
                "bot",
                1,
                [{"username": "bot"}],
            ),
            # No mentions in event
            (
                "issue_comment",
                {"comment": {"body": "No mentions here"}},
                None,
                0,
                [],
            ),
            # Multiple mentions, filter by username
            (
                "issue_comment",
                {"comment": {"body": "@bot1 help @bot2 deploy @user test"}},
                re.compile(r"bot\d"),
                2,
                [
                    {"username": "bot1"},
                    {"username": "bot2"},
                ],
            ),
            # Issue comment with issue data
            (
                "issue_comment",
                {"comment": {"body": "@bot help"}, "issue": {}},
                "bot",
                1,
                [{"username": "bot"}],
            ),
            # PR comment (issue_comment with pull_request)
            (
                "issue_comment",
                {"comment": {"body": "@bot help"}, "issue": {"pull_request": {}}},
                "bot",
                1,
                [{"username": "bot"}],
            ),
            # No username filter matches all mentions
            (
                "issue_comment",
                {"comment": {"body": "@alice review @bot help"}},
                None,
                2,
                [{"username": "alice"}, {"username": "bot"}],
            ),
            # Get all mentions with wildcard regex pattern
            (
                "issue_comment",
                {"comment": {"body": "@alice review @bob help"}},
                re.compile(r".*"),
                2,
                [
                    {"username": "alice"},
                    {"username": "bob"},
                ],
            ),
            # PR review comment
            (
                "pull_request_review_comment",
                {"comment": {"body": "@reviewer please check"}},
                "reviewer",
                1,
                [{"username": "reviewer"}],
            ),
            # Commit comment
            (
                "commit_comment",
                {"comment": {"body": "@bot test this commit"}},
                "bot",
                1,
                [{"username": "bot"}],
            ),
            # Empty comment body
            (
                "issue_comment",
                {"comment": {"body": ""}},
                None,
                0,
                [],
            ),
            # Mentions in code blocks (should be ignored)
            (
                "issue_comment",
                {"comment": {"body": "```\n@bot deploy\n```\n@bot help"}},
                "bot",
                1,
                [{"username": "bot"}],
            ),
        ],
    )
    def test_from_event(
        self,
        create_event,
        event_type,
        event_data,
        username,
        expected_count,
        expected_mentions,
    ):
        event = create_event(event_type, **event_data)
        scope = MentionScope.from_event(event)

        mentions = list(Mention.from_event(event, username=username, scope=scope))

        assert len(mentions) == expected_count
        for mention, expected in zip(mentions, expected_mentions, strict=False):
            assert mention.mention.username == expected["username"]
            assert mention.scope == scope
