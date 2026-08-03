import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class PendingOperation:
    # The owner is stored with the event so the cancel route can refuse an operation
    # that belongs to another actor — an operation_id alone is not an authorisation.
    actor_id: str
    cancel_event: asyncio.Event


# In-memory cancellation registry — maps operation_id to its pending operation.
# The streaming generator removes the entry when it finishes (cleanup) and the cancel
# route handler sets the event for a client-initiated cancellation.
# Single-task assumption: works correctly only with fastapi_desired_count = 1.
# Multi-task cancellation requires a distributed store (DynamoDB TTL item per op).
cancel_registry: dict[str, PendingOperation] = {}
