#!/usr/bin/env python3
"""
Backfill Langfuse with historical Moonshot request data.

Reads exported XLSX files from the Moonshot console (Request Details),
deduplicates by Request ID, calculates cost using official pricing,
and creates Langfuse traces + generations via the ingestion batch API.

Usage:
    python3 backfill-langfuse.py

Idempotent: uses deterministic trace/generation IDs derived from Moonshot
Request IDs, so re-running will update existing records.
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import openpyxl
from langfuse import Langfuse
from langfuse.api.resources.ingestion.types import (
    IngestionEvent_GenerationCreate,
    IngestionEvent_TraceCreate,
)
from langfuse.api.resources.ingestion.types.create_generation_body import CreateGenerationBody
from langfuse.api.resources.ingestion.types.trace_body import TraceBody

# ============================================
# CONFIG
# ============================================

EXPORTS_DIR = Path(__file__).parent / "moonshot-exports"

LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-atlas-local-observability")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "sk-atlas-local-observability")
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3100")

# Official Moonshot pricing (USD per 1M tokens)
# Source: https://platform.moonshot.ai/docs/pricing/chat
PRICING = {
    "kimi-k2.5": {"input": 0.60, "output": 3.00, "cached_input": 0.10},
    "kimi-k2-0905-preview": {"input": 0.60, "output": 3.00, "cached_input": 0.10},
    "moonshot-v1-32k": {"input": 0.22, "output": 0.22, "cached_input": 0.22},
    "moonshot-v1-8k": {"input": 0.11, "output": 0.11, "cached_input": 0.11},
    "default": {"input": 0.60, "output": 3.00, "cached_input": 0.10},
}

BATCH_SIZE = 20  # Events per API call (each record = 2 events: trace + generation)


def log(msg: str):
    print(f"[{datetime.now().isoformat()}] {msg}", flush=True)


def calculate_cost(model: str, input_tokens: int, output_tokens: int, cached_tokens: int) -> float:
    """Calculate cost in USD for a single request."""
    pricing = PRICING.get(model, PRICING["default"])
    non_cached_input = max(0, input_tokens - cached_tokens)
    cached_cost = cached_tokens * pricing["cached_input"] / 1_000_000
    input_cost = non_cached_input * pricing["input"] / 1_000_000
    output_cost = output_tokens * pricing["output"] / 1_000_000
    return cached_cost + input_cost + output_cost


def load_xlsx_files() -> dict:
    """Load all XLSX exports, deduplicate by Request ID."""
    records = {}

    xlsx_files = sorted(EXPORTS_DIR.glob("*.xlsx"))
    if not xlsx_files:
        log(f"No XLSX files found in {EXPORTS_DIR}")
        sys.exit(1)

    for xlsx_path in xlsx_files:
        log(f"Loading {xlsx_path.name}...")
        wb = openpyxl.load_workbook(xlsx_path)
        ws = wb.active

        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                continue  # Skip header

            request_id = row[0]
            if not request_id or not str(request_id).startswith("chatcmpl-"):
                continue

            model = row[1] or "kimi-k2.5"
            created_at = row[2]
            input_tokens = int(row[3] or 0)
            output_tokens = int(row[4] or 0)
            cached_tokens = int(row[5] or 0)

            records[request_id] = {
                "request_id": request_id,
                "model": model,
                "created_at": created_at,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cached_tokens": cached_tokens,
            }

        wb.close()
        log(f"  Loaded, total unique records so far: {len(records)}")

    return records


def to_utc(dt: datetime) -> datetime:
    """Convert Moonshot timestamp (UTC+8) to UTC."""
    if dt.tzinfo is None:
        return (dt - timedelta(hours=8)).replace(tzinfo=timezone.utc)
    return dt


def backfill_langfuse(records: dict):
    """Create Langfuse traces and generations via batch ingestion API."""
    langfuse = Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST,
    )

    sorted_records = sorted(records.values(), key=lambda x: x["created_at"])
    total = len(sorted_records)
    total_cost = 0.0
    total_input = 0
    total_output = 0
    total_cached = 0

    log(f"Backfilling {total} records into Langfuse at {LANGFUSE_HOST}...")

    batch = []
    batch_count = 0

    for i, rec in enumerate(sorted_records):
        request_id = rec["request_id"]
        model = rec["model"]
        created_at_utc = to_utc(rec["created_at"])
        input_tokens = rec["input_tokens"]
        output_tokens = rec["output_tokens"]
        cached_tokens = rec["cached_tokens"]

        cost = calculate_cost(model, input_tokens, output_tokens, cached_tokens)
        total_cost += cost
        total_input += input_tokens
        total_output += output_tokens
        total_cached += cached_tokens

        trace_id = f"backfill-{request_id}"
        gen_id = f"gen-{request_id}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # Create trace event
        trace_event = IngestionEvent_TraceCreate(
            id=str(uuid.uuid4()),
            timestamp=now_iso,
            body=TraceBody(
                id=trace_id,
                timestamp=created_at_utc,
                name="nova-conversation",
                sessionId="backfill-historical",
                metadata={"source": "moonshot-export-backfill", "moonshot_request_id": request_id},
                tags=["backfill"],
            ),
        )

        # Create generation event
        gen_event = IngestionEvent_GenerationCreate(
            id=str(uuid.uuid4()),
            timestamp=now_iso,
            body=CreateGenerationBody(
                id=gen_id,
                traceId=trace_id,
                name="llm-call",
                model=f"openai/{model}",
                startTime=created_at_utc,
                endTime=created_at_utc,
                usageDetails={
                    "input": input_tokens,
                    "output": output_tokens,
                    "total": input_tokens + output_tokens,
                    "cache_read_input_tokens": cached_tokens,
                },
                costDetails={"total": cost},
                metadata={
                    "moonshot_request_id": request_id,
                    "backfill": True,
                },
            ),
        )

        batch.extend([trace_event, gen_event])

        # Send batch when full
        if len(batch) >= BATCH_SIZE * 2:
            resp = langfuse.api.ingestion.batch(batch=batch)
            successes = sum(1 for s in resp.successes) if resp.successes else 0
            errors = sum(1 for e in resp.errors) if resp.errors else 0
            batch_count += 1
            if errors > 0:
                log(f"  Batch {batch_count}: {successes} ok, {errors} errors")
                for err in (resp.errors or [])[:3]:
                    log(f"    Error: {err}")
            batch = []

        if (i + 1) % 100 == 0:
            log(f"  Progress: {i + 1}/{total} ({(i + 1) / total * 100:.1f}%)")

    # Send remaining events
    if batch:
        resp = langfuse.api.ingestion.batch(batch=batch)
        batch_count += 1

    log(f"\n=== Backfill Summary ===")
    log(f"  Total records: {total}")
    log(f"  API batches sent: {batch_count}")
    log(f"  Total input tokens: {total_input:,}")
    log(f"  Total output tokens: {total_output:,}")
    log(f"  Total cached tokens: {total_cached:,}")
    log(f"  Total calculated cost: ${total_cost:.5f}")
    log(f"  Average cost per call: ${total_cost / total:.6f}")


def main():
    log("=== Langfuse Backfill Starting ===")
    log(f"Exports directory: {EXPORTS_DIR}")
    log(f"Langfuse host: {LANGFUSE_HOST}")

    records = load_xlsx_files()
    if not records:
        log("No records to backfill")
        sys.exit(0)

    backfill_langfuse(records)
    log("=== Langfuse Backfill Complete ===")


if __name__ == "__main__":
    main()
