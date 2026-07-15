from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "deploy-agentcore" / "agents" / "memory_support.py"
SPEC = importlib.util.spec_from_file_location("memory_support", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {MODULE_PATH}")
memory_support = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(memory_support)


class Agent:
    def __init__(self, messages: list[dict], state: dict):
        self.messages = messages
        self.state = state


class Event:
    def __init__(self, agent: Agent):
        self.agent = agent


class AwsFailure(RuntimeError):
    def __init__(self):
        super().__init__("secret-memory-content")
        self.response = {"Error": {"Code": "ValidationException"}}


def user_event(text: str = "Quelles sont mes préférences ?") -> Event:
    return Event(
        Agent(
            messages=[{"role": "user", "content": [{"text": text}]}],
            state={"actor_id": "user-123", "session_id": "session-123"},
        )
    )


class PreferenceMemorySupportTests(unittest.TestCase):
    def setUp(self) -> None:
        class FakeBase:
            HookProvider = object
            PHASE4_SYSTEM_PROMPT_BASE = "Base prompt.\n"
            logger = MagicMock()

            @staticmethod
            def safe_hash(value: str) -> str:
                return f"hash-{value}"

        self.base = FakeBase
        memory_support.configure_runtime_memory(self.base)
        self.hook_class = self.base.TravelAgentMemoryHooks

    def test_configures_actor_scoped_namespace_and_truthful_trip_language(self) -> None:
        hook = self.hook_class("memory-1", MagicMock())

        self.assertEqual(hook.namespace, "/travel/{actorId}/preferences")
        self.assertIn("only record and manage travel plans", self.base.PHASE4_SYSTEM_PROMPT_BASE)
        self.assertIn("Never claim", self.base.PHASE4_SYSTEM_PROMPT_BASE)
        self.assertIn("booked", self.base.PHASE4_SYSTEM_PROMPT_BASE)

    def test_logs_empty_retrieval_without_exposing_query(self) -> None:
        client = MagicMock()
        client.retrieve_memories.return_value = []
        event = user_event("private preference query")
        hook = self.hook_class("memory-1", client)

        hook.retrieve_user_context(event)

        client.retrieve_memories.assert_called_once_with(
            memory_id="memory-1",
            namespace="/travel/user-123/preferences",
            query="private preference query",
            top_k=3,
        )
        log_payload = json.loads(self.base.logger.info.call_args.args[0])
        self.assertEqual(log_payload["event"], "memory_retrieval_empty")
        self.assertNotIn("private preference query", self.base.logger.info.call_args.args[0])

    def test_injects_retrieved_preferences_as_untrusted_data(self) -> None:
        client = MagicMock()
        client.retrieve_memories.return_value = [
            {"content": {"text": "Prefers quiet hotels"}},
            {"content": {"text": "Vegetarian"}},
        ]
        event = user_event()
        hook = self.hook_class("memory-1", client)

        hook.retrieve_user_context(event)

        text = event.agent.messages[-1]["content"][0]["text"]
        self.assertIn("Untrusted user memory data", text)
        self.assertIn("Prefers quiet hotels", text)
        self.assertIn("Current Query: Quelles sont mes préférences ?", text)
        log_payload = json.loads(self.base.logger.info.call_args.args[0])
        self.assertEqual(log_payload["event"], "memory_retrieved")
        self.assertEqual(log_payload["count"], 2)

    def test_retrieval_error_log_is_redacted(self) -> None:
        client = MagicMock()
        client.retrieve_memories.side_effect = AwsFailure()
        hook = self.hook_class("memory-1", client)

        hook.retrieve_user_context(user_event())

        raw_log = self.base.logger.warning.call_args.args[0]
        log_payload = json.loads(raw_log)
        self.assertEqual(log_payload["event"], "memory_retrieval_failed")
        self.assertEqual(log_payload["aws_error_code"], "ValidationException")
        self.assertNotIn("secret-memory-content", raw_log)

    def test_saves_latest_interaction_with_actor_and_session(self) -> None:
        client = MagicMock()
        event = Event(
            Agent(
                messages=[
                    {"role": "user", "content": [{"text": "Je préfère le train"}]},
                    {"role": "assistant", "content": [{"text": "Compris"}]},
                ],
                state={"actor_id": "user-123", "session_id": "session-123"},
            )
        )
        hook = self.hook_class("memory-1", client)

        hook.save_interaction(event)

        client.create_event.assert_called_once_with(
            memory_id="memory-1",
            actor_id="user-123",
            session_id="session-123",
            messages=[("Je préfère le train", "USER"), ("Compris", "ASSISTANT")],
        )
        log_payload = json.loads(self.base.logger.info.call_args.args[0])
        self.assertEqual(log_payload["event"], "memory_saved")

    def test_save_error_log_is_redacted(self) -> None:
        client = MagicMock()
        client.create_event.side_effect = AwsFailure()
        event = Event(
            Agent(
                messages=[
                    {"role": "user", "content": [{"text": "private"}]},
                    {"role": "assistant", "content": [{"text": "secret"}]},
                ],
                state={"actor_id": "user-123", "session_id": "session-123"},
            )
        )
        hook = self.hook_class("memory-1", client)

        hook.save_interaction(event)

        raw_log = self.base.logger.warning.call_args.args[0]
        log_payload = json.loads(raw_log)
        self.assertEqual(log_payload["event"], "memory_save_failed")
        self.assertEqual(log_payload["aws_error_code"], "ValidationException")
        self.assertNotIn("private", raw_log)
        self.assertNotIn("secret", raw_log)


if __name__ == "__main__":
    unittest.main()
