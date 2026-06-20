"""Structured logging for OCR pipeline — JSON format for analysis and debugging.

Importers: _stage_1_extract.py calls OCRLogger() for High improvement #2 (structured logging)
User instruction: "按照从高到低的优先级，依次实施改进" → implementing HIGH priority improvements
Data schema: JSONL format (one JSON object per line) with timestamp, session_id, event_type, metrics
"""

import json
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Optional


class OCRLogger:
    """Structured logger for OCR operations — writes JSONL for easy analysis."""

    def __init__(self, log_dir: Path):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "ocr_log.jsonl"
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def log_event(self, event_type: str, **kwargs):
        """Log a structured event as JSON.

        Args:
            event_type: Type of event (e.g., 'chunk_start', 'chunk_complete', 'error')
            **kwargs: Event-specific data
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "event_type": event_type,
            **kwargs
        }
        # Append to JSONL file (one JSON object per line)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log_chunk_start(self, chunk_idx: int, total_chunks: int, pages: str):
        """Log chunk processing start."""
        self.log_event("chunk_start", chunk_idx=chunk_idx, total_chunks=total_chunks, pages=pages)

    def log_chunk_complete(self, chunk_idx: int, total_chunks: int, elapsed_sec: float,
                          chars_extracted: int, images_extracted: int):
        """Log chunk processing completion."""
        self.log_event(
            "chunk_complete",
            chunk_idx=chunk_idx,
            total_chunks=total_chunks,
            elapsed_sec=round(elapsed_sec, 2),
            chars_extracted=chars_extracted,
            images_extracted=images_extracted,
            chars_per_sec=round(chars_extracted / max(elapsed_sec, 0.1), 1)
        )

    def log_chunk_error(self, chunk_idx: int, total_chunks: int, error: str,
                       attempt: int, max_attempts: int):
        """Log chunk processing error."""
        self.log_event(
            "chunk_error",
            chunk_idx=chunk_idx,
            total_chunks=total_chunks,
            error=str(error)[:200],
            attempt=attempt,
            max_attempts=max_attempts
        )

    def log_json_truncation(self, batch_idx: int, response_length: int,
                           recovered_count: int, total_count: int):
        """Log JSON truncation recovery."""
        self.log_event(
            "json_truncation",
            batch_idx=batch_idx,
            response_length=response_length,
            recovered_count=recovered_count,
            total_count=total_count,
            recovery_rate=round(recovered_count / max(total_count, 1) * 100, 1)
        )

    def log_caption_batch(self, batch_idx: int, total_batches: int,
                         elapsed_sec: float, success_count: int, total_count: int):
        """Log caption batch completion."""
        self.log_event(
            "caption_batch",
            batch_idx=batch_idx,
            total_batches=total_batches,
            elapsed_sec=round(elapsed_sec, 2),
            success_count=success_count,
            total_count=total_count,
            success_rate=round(success_count / max(total_count, 1) * 100, 1)
        )

    def log_warmup(self, elapsed_sec: float, success: bool, error: Optional[str] = None):
        """Log warmup phase."""
        self.log_event(
            "warmup",
            elapsed_sec=round(elapsed_sec, 2),
            success=success,
            error=error
        )

    def get_summary(self) -> dict:
        """Generate summary statistics from log file."""
        if not self.log_file.exists():
            return {}

        summary = {
            "total_chunks": 0,
            "successful_chunks": 0,
            "failed_chunks": 0,
            "total_time_sec": 0.0,
            "avg_chunk_time_sec": 0.0,
            "total_chars_extracted": 0,
            "total_images_extracted": 0,
            "json_truncations": 0,
        }

        chunk_times = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("event_type") == "chunk_complete":
                        summary["successful_chunks"] += 1
                        summary["total_chunks"] += 1
                        elapsed = entry.get("elapsed_sec", 0)
                        chunk_times.append(elapsed)
                        summary["total_time_sec"] += elapsed
                        summary["total_chars_extracted"] += entry.get("chars_extracted", 0)
                        summary["total_images_extracted"] += entry.get("images_extracted", 0)
                    elif entry.get("event_type") == "chunk_error":
                        summary["failed_chunks"] += 1
                        summary["total_chunks"] += 1
                    elif entry.get("event_type") == "json_truncation":
                        summary["json_truncations"] += 1
                except json.JSONDecodeError:
                    pass

        if chunk_times:
            summary["avg_chunk_time_sec"] = round(sum(chunk_times) / len(chunk_times), 2)

        return summary
