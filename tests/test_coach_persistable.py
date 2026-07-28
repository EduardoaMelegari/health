import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import coach


class FakeTextBlock:
    def __init__(self, text, parsed_output=None):
        self.type = "text"
        self.text = text
        self._parsed_output = parsed_output

    def model_dump(self):
        data = {"type": "text", "text": self.text}
        if self._parsed_output is not None:
            data["text"] = {"text": self.text, "parsed_output": self._parsed_output}
        return data


class FakeToolUseBlock:
    def __init__(self):
        self.type = "tool_use"
        self.id = "tool_1"
        self.name = "log_food"
        self.input = {"food": "arroz"}

    def model_dump(self):
        return {
            "type": "tool_use",
            "id": self.id,
            "name": self.name,
            "input": self.input,
            "parsed_output": {"unexpected": True},
        }


class PersistableTests(unittest.TestCase):
    def test_persistable_sanitizes_sdk_specific_fields(self):
        blocks = [FakeTextBlock("olá", parsed_output={"ok": True}), FakeToolUseBlock()]

        persisted = coach._persistable(blocks)

        self.assertEqual(persisted[0], {"type": "text", "text": "olá"})
        self.assertEqual(persisted[1], {"type": "tool_use", "id": "tool_1", "name": "log_food", "input": {"food": "arroz"}})


if __name__ == "__main__":
    unittest.main()
