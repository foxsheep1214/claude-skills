#!/usr/bin/env python3
"""OCR performance analysis — benchmark suite for small/medium/large files.

Importers: Manual execution via CLI for performance analysis after ingest
User instruction: HIGH improvement #3 — performance benchmark/analytics
Data schema: JSONL logs → JSON report with statistics and performance metrics
"""

import json
import sys
from pathlib import Path
from statistics import mean, median, stdev
from typing import Optional


def analyze_ocr_log(log_file: Path) -> dict:
    """Analyze ocr_log.jsonl and generate performance report."""
    if not log_file.exists():
        return {"error": f"Log file not found: {log_file}"}

    # Parse JSONL
    events = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not events:
        return {"error": "No events found in log"}

    # Analyze chunks
    chunks = [e for e in events if e.get("event_type") == "chunk_complete"]
    errors = [e for e in events if e.get("event_type") == "chunk_error"]
    truncations = [e for e in events if e.get("event_type") == "json_truncation"]

    if not chunks:
        return {"error": "No completed chunks in log"}

    chunk_times = [c.get("elapsed_sec", 0) for c in chunks]
    chunk_chars = [c.get("chars", 0) for c in chunks]
    total_chars = sum(chunk_chars)
    total_time = sum(chunk_times)

    # Calculate statistics
    stats = {
        "summary": {
            "total_chunks": len(chunks),
            "failed_chunks": len(errors),
            "success_rate": round(len(chunks) / (len(chunks) + len(errors)) * 100, 1) if (len(chunks) + len(errors)) > 0 else 0,
            "total_time_sec": round(total_time, 2),
            "total_chars_extracted": total_chars,
            "throughput_chars_per_sec": round(total_chars / max(total_time, 0.1), 1),
        },
        "chunk_performance": {
            "chunk_count": len(chunk_times),
            "min_time_sec": round(min(chunk_times), 2),
            "max_time_sec": round(max(chunk_times), 2),
            "avg_time_sec": round(mean(chunk_times), 2),
            "median_time_sec": round(median(chunk_times), 2),
            "stdev_time_sec": round(stdev(chunk_times), 2) if len(chunk_times) > 1 else 0,
        },
        "character_extraction": {
            "total_chars": total_chars,
            "avg_chars_per_chunk": round(mean(chunk_chars), 0) if chunk_chars else 0,
            "chars_per_second": round(total_chars / max(total_time, 0.1), 1),
        },
    }

    if truncations:
        recovery_rates = [
            t.get("recovered", 0) / max(t.get("total", 1), 1) * 100
            for t in truncations
        ]
        stats["json_recovery"] = {
            "truncation_count": len(truncations),
            "avg_recovery_rate": round(mean(recovery_rates), 1),
            "min_recovery_rate": round(min(recovery_rates), 1),
            "max_recovery_rate": round(max(recovery_rates), 1),
        }

    if errors:
        stats["errors"] = {
            "error_count": len(errors),
            "first_chunk": min(e.get("chunk", 0) for e in errors),
            "last_chunk": max(e.get("chunk", 0) for e in errors),
        }

    # Performance classification
    file_size = "unknown"
    if 50 <= len(chunks) <= 100:
        file_size = "large"
    elif 10 <= len(chunks) < 50:
        file_size = "medium"
    else:
        file_size = "small"

    stats["file_classification"] = {
        "chunk_count": len(chunks),
        "estimated_size": file_size,
        "estimated_pages": len(chunks) * 50,
    }

    return stats


def format_report(stats: dict) -> str:
    """Format statistics as human-readable report."""
    if "error" in stats:
        return f"❌ Error: {stats['error']}"

    report = []
    report.append("\n" + "=" * 70)
    report.append("OCR PERFORMANCE ANALYSIS REPORT")
    report.append("=" * 70)

    summary = stats.get("summary", {})
    report.append("\n📊 SUMMARY")
    report.append(f"  Total time:           {summary.get('total_time_sec')} sec")
    report.append(f"  Chunks processed:     {summary.get('total_chunks')}")
    report.append(f"  Success rate:         {summary.get('success_rate')}%")
    report.append(f"  Characters extracted: {summary.get('total_chars_extracted'):,}")
    report.append(f"  Throughput:           {summary.get('throughput_chars_per_sec'):,} chars/sec")

    chunk_perf = stats.get("chunk_performance", {})
    report.append("\n⏱️  CHUNK PERFORMANCE")
    report.append(f"  Chunk count:          {chunk_perf.get('chunk_count')}")
    report.append(f"  Min time:             {chunk_perf.get('min_time_sec')} sec")
    report.append(f"  Max time:             {chunk_perf.get('max_time_sec')} sec")
    report.append(f"  Avg time:             {chunk_perf.get('avg_time_sec')} sec")
    report.append(f"  Median time:          {chunk_perf.get('median_time_sec')} sec")

    char_ext = stats.get("character_extraction", {})
    report.append("\n📄 CHARACTER EXTRACTION")
    report.append(f"  Total chars:          {char_ext.get('total_chars'):,}")
    report.append(f"  Avg per chunk:        {char_ext.get('avg_chars_per_chunk'):,.0f}")

    if "json_recovery" in stats:
        recovery = stats["json_recovery"]
        report.append("\n🔧 JSON RECOVERY")
        report.append(f"  Truncations:          {recovery.get('truncation_count')}")
        report.append(f"  Avg recovery rate:    {recovery.get('avg_recovery_rate')}%")

    file_class = stats.get("file_classification", {})
    report.append("\n📦 FILE CLASSIFICATION")
    report.append(f"  Estimated size:       {file_class.get('estimated_size')}")
    report.append(f"  Estimated pages:      {file_class.get('estimated_pages')}")

    report.append("\n" + "=" * 70 + "\n")
    return "\n".join(report)


def save_report(stats: dict, output_file: Optional[Path] = None) -> None:
    """Save statistics to JSON file."""
    if output_file is None:
        output_file = Path("ocr_performance_report.json")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"✅ Report saved to {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_ocr_performance.py <log_file> [--report <output_file>]")
        print("\nExample:")
        print("  python analyze_ocr_performance.py extract-tmp/ocr_log.jsonl")
        sys.exit(1)

    log_file = Path(sys.argv[1])
    output_file = None

    if "--report" in sys.argv:
        idx = sys.argv.index("--report")
        if idx + 1 < len(sys.argv):
            output_file = Path(sys.argv[idx + 1])

    stats = analyze_ocr_log(log_file)
    print(format_report(stats))

    if output_file:
        save_report(stats, output_file)
