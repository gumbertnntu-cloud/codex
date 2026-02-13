import unittest

from tjr.core.input_parser import (
    parse_chat_sources_list,
    parse_chat_sources_text,
    parse_search_terms_text,
    parse_user_list_input,
)


class InputParserTests(unittest.TestCase):
    def test_parser_supports_newline_and_comma(self) -> None:
        values = parse_user_list_input("chat1, chat2\nchat3; chat4", lowercase=False)
        self.assertEqual(values, ["chat1", "chat2", "chat3", "chat4"])

    def test_parser_lowercase_mode(self) -> None:
        values = parse_user_list_input("Director, Директор", lowercase=True)
        self.assertEqual(values, ["director", "директор"])

    def test_parse_chat_sources_text_supports_space_separated_handles(self) -> None:
        values = parse_chat_sources_text("@a @b @c")
        self.assertEqual(values, ["@a", "@b", "@c"])

    def test_parse_chat_sources_list_splits_legacy_single_item_value(self) -> None:
        values = parse_chat_sources_list(["@topmanager_exclusive @workfortop @careerfedoroff"])
        self.assertEqual(values, ["@topmanager_exclusive", "@workfortop", "@careerfedoroff"])

    def test_parse_chat_sources_list_dedupes_same_chat(self) -> None:
        values = parse_chat_sources_list(["@rudakovahr", "@rudakovahr", "https://t.me/rudakovahr"])
        self.assertEqual(values, ["@rudakovahr"])

    def test_parse_chat_sources_list_keeps_chat_and_specific_message(self) -> None:
        values = parse_chat_sources_list(["@rudakovahr", "https://t.me/rudakovahr/7378"])
        self.assertEqual(values, ["@rudakovahr", "https://t.me/rudakovahr/7378"])

    def test_parse_search_terms_text_supports_slash_separator(self) -> None:
        values = parse_search_terms_text("ceo/исполнительный директор/операционный директор")
        self.assertEqual(values, ["ceo", "исполнительный директор", "операционный директор"])


if __name__ == "__main__":
    unittest.main()
