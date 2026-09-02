from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

Scope = StrEnum("Scope", ["IP", "USER"])


@dataclass(frozen=True, slots=True)
class Policy:
    name: str
    capacity: int
    refill_per_second: float
    scope: Scope

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ValueError("capacity must be at least 1; a bucket of 0 denies everything")
        if self.refill_per_second <= 0:
            raise ValueError("refill_per_second must be positive; 0 divides by zero in the script")


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    remaining: float
    retry_after_seconds: float


class Limiter(Protocol):
    async def check(self, policy: Policy, identity: str, *, now: float) -> Decision: ...
