import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.cli_backend import AgentCommand, build_agent_command, run_agent_for_messages


class CopilotBackendTests(unittest.TestCase):
    def test_builds_copilot_json_command(self):
        command = build_agent_command(
            model="gpt-5.6-sol",
            prompt="analyze this function",
            cwd="/tmp/project",
            backend="copilot-cli",
            effort="high",
        )

        self.assertEqual(command.backend, "copilot-cli")
        self.assertEqual(command.stdin, "analyze this function")
        self.assertIn("--output-format", command.argv)
        self.assertIn("json", command.argv)
        self.assertIn("--no-ask-user", command.argv)
        self.assertIn("--allow-all", command.argv)
        self.assertIn("gpt-5.6-sol", command.argv)
        self.assertIn("high", command.argv)

    @patch("src.cli_backend.subprocess.run")
    @patch("src.cli_backend.build_agent_command")
    def test_extracts_final_copilot_message_and_usage(self, build_command, run):
        build_command.return_value = AgentCommand(
            argv=["copilot"],
            stdin="prompt",
            backend="copilot-cli",
        )
        events = [
            {"type": "assistant.message", "data": {"phase": "analysis", "content": "draft"}},
            {
                "type": "assistant.message",
                "data": {"phase": "final_answer", "content": '{"status":"supported"}'},
            },
            {"type": "result", "usage": {"input_tokens": 10, "output_tokens": 4}},
        ]
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout="\n".join(json.dumps(event) for event in events),
            stderr="",
        )

        content, usage = run_agent_for_messages(
            "gpt-5.6-sol",
            [{"role": "user", "content": "return JSON"}],
        )

        self.assertEqual(content, '{"status":"supported"}')
        self.assertEqual(usage, {"input_tokens": 10, "output_tokens": 4})

    @patch("src.cli_backend.subprocess.run")
    @patch("src.cli_backend.build_agent_command")
    def test_rejects_copilot_output_without_final_message(self, build_command, run):
        build_command.return_value = AgentCommand(
            argv=["copilot"],
            stdin="prompt",
            backend="copilot-cli",
        )
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"type": "result", "usage": {}}),
            stderr="",
        )

        with self.assertRaisesRegex(RuntimeError, "final assistant message"):
            run_agent_for_messages("gpt-5.6-sol", [{"role": "user", "content": "return JSON"}])


if __name__ == "__main__":
    unittest.main()
