from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHAT_SERVICE = (ROOT / "frontend" / "src" / "services" / "chatService.ts").read_text(
    encoding="utf-8"
)
CHAT_CONTAINER = (
    ROOT / "frontend" / "src" / "components" / "Chat" / "ChatContainer.tsx"
).read_text(encoding="utf-8")


class FrontendOperationContractTests(unittest.TestCase):
    def test_ambiguous_errors_keep_the_operation_identifier(self) -> None:
        self.assertIn("export class AgentRequestError", CHAT_SERVICE)
        self.assertIn("readonly operationId: string", CHAT_SERVICE)
        self.assertIn("isAmbiguousStatus", CHAT_SERVICE)
        self.assertIn(
            "new AgentRequestError('Request timed out', operationId, true)",
            CHAT_SERVICE,
        )

    def test_operation_is_persisted_before_the_network_call(self) -> None:
        persist = "writePendingOperations(sessionId, pendingOperations);"
        send = "const response = await sendMessage("
        self.assertIn("pendingOperations[fingerprint] = operationId", CHAT_CONTAINER)
        self.assertLess(CHAT_CONTAINER.index(persist), CHAT_CONTAINER.index(send))
        self.assertIn("existingOperationId ?? uuidv4()", CHAT_CONTAINER)

    def test_prompt_content_is_not_written_to_session_storage(self) -> None:
        self.assertIn("messageFingerprint", CHAT_CONTAINER)
        self.assertIn("window.crypto.subtle.digest('SHA-256'", CHAT_CONTAINER)
        self.assertNotIn("message: normalizedMessage", CHAT_CONTAINER)


if __name__ == "__main__":
    unittest.main()
