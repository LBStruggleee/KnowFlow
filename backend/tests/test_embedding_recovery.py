from app.services.embedding_service import (
    FALLBACK_COOLDOWN_SECONDS,
    HashingEmbeddingService,
    ResilientEmbeddingService,
)
from fastapi import HTTPException

DIMENSION = 384


class _FlakyRemoteProvider:
    index_name = "unavailable_remote"

    def __init__(self, fail: bool = True) -> None:
        self.fail = fail
        self.calls = 0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail:
            raise HTTPException(status_code=502, detail="remote unavailable")
        return [[0.5] * DIMENSION for _ in texts]


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_default_cooldown_is_sixty_seconds() -> None:
    assert FALLBACK_COOLDOWN_SECONDS == 60.0


def test_failure_switches_to_fallback_and_logs_warning(caplog) -> None:
    remote = _FlakyRemoteProvider(fail=True)
    service = ResilientEmbeddingService(remote, HashingEmbeddingService())

    with caplog.at_level("WARNING"):
        vectors = service.embed_texts(["Spark RDD lineage"])

    assert service.index_name == "hashing_v1"
    assert len(vectors) == 1
    assert len(vectors[0]) == DIMENSION
    assert any("switching to local hashing" in record.message for record in caplog.records)


def test_requests_stay_on_fallback_during_cooldown() -> None:
    clock = _FakeClock()
    remote = _FlakyRemoteProvider(fail=True)
    service = ResilientEmbeddingService(
        remote,
        HashingEmbeddingService(),
        cooldown_seconds=60.0,
        clock=clock,
    )
    service.embed_texts(["first"])  # triggers the initial switch
    assert remote.calls == 1

    clock.advance(59.9)
    service.embed_texts(["second"])

    assert remote.calls == 1, "probe must wait for the cooldown to elapse"
    assert service.index_name == "hashing_v1"


def test_after_cooldown_successful_probe_switches_back(caplog) -> None:
    clock = _FakeClock()
    remote = _FlakyRemoteProvider(fail=True)
    service = ResilientEmbeddingService(
        remote,
        HashingEmbeddingService(),
        cooldown_seconds=60.0,
        clock=clock,
    )
    service.embed_texts(["first"])
    remote.fail = False
    clock.advance(60.0)

    with caplog.at_level("WARNING"):
        vectors = service.embed_texts(["second"])

    assert remote.calls == 2
    assert service.index_name == "unavailable_remote"
    assert vectors == [[0.5] * DIMENSION]
    assert any("recovered" in record.message for record in caplog.records)


def test_failed_probe_restarts_cooldown_and_stays_on_fallback() -> None:
    clock = _FakeClock()
    remote = _FlakyRemoteProvider(fail=True)
    service = ResilientEmbeddingService(
        remote,
        HashingEmbeddingService(),
        cooldown_seconds=60.0,
        clock=clock,
    )
    service.embed_texts(["first"])
    clock.advance(60.0)
    service.embed_texts(["second"])  # probe fails again
    assert remote.calls == 2

    clock.advance(1.0)
    service.embed_texts(["third"])
    assert remote.calls == 2, "a failed probe must restart the cooldown"

    clock.advance(60.0)
    service.embed_texts(["fourth"])
    assert remote.calls == 3
    assert service.index_name == "hashing_v1"
