from __future__ import annotations

from django_github_app.commands import check_event_for_mention
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
        event = {"comment": {"body": "@bot help"}}

        assert check_event_for_mention(event, "help", "bot") is True
        assert check_event_for_mention(event, "deploy", "bot") is False

    def test_match_without_command(self):
        event = {"comment": {"body": "@bot help"}}

        assert check_event_for_mention(event, None, "bot") is True

        event = {"comment": {"body": "no mention here"}}

        assert check_event_for_mention(event, None, "bot") is False

    def test_no_comment_body(self):
        event = {}

        assert check_event_for_mention(event, "help", "bot") is False

        event = {"comment": {}}

        assert check_event_for_mention(event, "help", "bot") is False

    def test_case_insensitive_command_match(self):
        event = {"comment": {"body": "@bot HELP"}}

        assert check_event_for_mention(event, "help", "bot") is True
        assert check_event_for_mention(event, "HELP", "bot") is True

    def test_multiple_mentions(self):
        event = {"comment": {"body": "@bot help @bot deploy"}}

        assert check_event_for_mention(event, "help", "bot") is True
        assert check_event_for_mention(event, "deploy", "bot") is True
        assert check_event_for_mention(event, "test", "bot") is False
