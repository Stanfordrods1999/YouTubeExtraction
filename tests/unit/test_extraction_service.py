"""Unit tests for ExtractionService: the fetch-failure short-circuit, source
status transitions, and token-usage capture from the include_raw decomposer.
The chat model and fetch tiers are mocked — no network."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.services.extractionService import (
    AtomicUnit,
    ExtractionService,
    UnitsResponse,
)

MODULE = "src.app.services.extractionService"


def make_repo():
    repo = MagicMock()
    repo.createExtractions = AsyncMock(return_value=[{"id": "run-1"}])
    repo.updateSourceStatus = AsyncMock()
    return repo


def make_service(repo, decomposer_result=None, decomposer_error=None):
    with patch(f"{MODULE}.ChatOpenAI") as MockChat:
        decomposer = MagicMock()
        if decomposer_error is not None:
            decomposer.ainvoke = AsyncMock(side_effect=decomposer_error)
        else:
            decomposer.ainvoke = AsyncMock(return_value=decomposer_result)
        MockChat.return_value.with_structured_output.return_value = decomposer
        svc = ExtractionService("top-1", "https://x.example", "src-1", repo)
    return svc


@pytest.mark.asyncio
async def test_total_fetch_failure_records_failed_run_and_skips_llm():
    repo = make_repo()
    svc = make_service(repo)
    svc.sourceHTML = AsyncMock(return_value=(None, None))

    out = await svc.extract()

    assert out == [{"id": "run-1"}]
    _, kwargs = repo.createExtractions.await_args
    assert kwargs["status"] == "failed"
    assert kwargs["failure_reason"] == "fetch_failed"
    repo.updateSourceStatus.assert_awaited_once_with(["src-1"], "failed")
    svc.decomposer.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_extract_records_strategy_usage_and_marks_extracted():
    repo = make_repo()
    raw = MagicMock()
    raw.usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    svc = make_service(repo, decomposer_result={
        "raw": raw,
        "parsed": UnitsResponse(units=[AtomicUnit(text="a fact", kind="fact")]),
        "parsing_error": None,
    })
    svc.sourceHTML = AsyncMock(return_value=("<html><body>enough</body></html>", "curl"))
    svc.build_extraction_input = MagicMock(
        return_value={"readable_text": "text", "structured": []}
    )

    await svc.extract()

    args, kwargs = repo.createExtractions.await_args
    assert args[0] == "src-1" and args[1] == "top-1"
    assert args[2] == [{"source_id": "src-1", "topic_id": "top-1",
                        "text": "a fact", "kind": "fact"}]
    assert kwargs["status"] == "completed"
    assert kwargs["extraction_strategy"] == "curl"
    assert kwargs["usage"] == {"input_tokens": 10, "output_tokens": 5,
                               "total_tokens": 15}
    repo.updateSourceStatus.assert_awaited_once_with(["src-1"], "extracted")


@pytest.mark.asyncio
async def test_unparseable_decomposition_yields_no_units_but_keeps_usage():
    raw = MagicMock()
    raw.usage_metadata = {"total_tokens": 7}
    svc = make_service(make_repo(), decomposer_result={
        "raw": raw, "parsed": None, "parsing_error": ValueError("bad json"),
    })

    units, usage = await svc._make_atomic_units(
        {"readable_text": "text", "structured": []}
    )

    assert units == []
    assert usage == {"total_tokens": 7}


@pytest.mark.asyncio
async def test_decomposer_exception_yields_empty_units_and_usage():
    svc = make_service(make_repo(), decomposer_error=RuntimeError("model down"))

    units, usage = await svc._make_atomic_units(
        {"readable_text": "text", "structured": []}
    )

    assert units == []
    assert usage == {}
