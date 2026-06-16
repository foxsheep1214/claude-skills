"""ingest_patch.py — Archive reference for conversation-mode chunk processing.

This file is NOT an executable script. It contains code snippets used as
reference during the 2026-06-15 conversation-mode ingest development.
The patterns here were later integrated into ingest.py's Stage 1.5.

Do NOT import or execute this file directly.
"""

# Modified phase2_chunk_analysis for one-chunk-per-call

# Replace the chunk_analysis function (around line 639)
# Original code output stage 1 outputs

# New code outputs stage 1 outputs one chunk at a time
# Modified phase2_chunk_analysis - exit 101 after each chunk

# Find and replace the chunk_analysis function
# Original code outputs all chunks, exits 101
# New code: outputs one chunk, waits for input, exits 101

# Original code stage 1 outputs one chunk

# Find the old chunk_analysis function and append the new one
# The old code is around line 639
# Insert new code at the end

# Old code:
if config.delegate_mode:
    for i, chunk in enumerate(chunks):
        ...
        print(f"\n⏸️ Enter to continue processing chunk {i+1}...")
        input()

# New code:
if config.delegate_mode:
    # Delegate mode: process one chunk at a time
    for i, chunk in enumerate(chunks):
        print(f"[phase2]   chunk {i+1}/{chunk_total} ({len(chunk):,} chars)...", end=" ", flush=True)
        prompt = build_chunk_analysis_prompt(chunk, i, chunk_total, global_digest, file_path, config)
        stage = f"phase2_chunk_{i+1}"

        # Save as a task file (not checkpoint)
        task_file = checkpoint_path.with_name(f"task_{i+1}.json")
        task_data = {
            "stage": stage,
            "extracted_text": extracted_text,
            "global_digest": global_digest,
            "chunk_index": i,
            "chunk_total": chunk_total,
            "chunk_text": chunk,
        }
        with open(task_file, "w", encoding="utf-8") as f:
            json.dumps(task_data, f, ensure_ascii=False, indent=2)

        # Process here (call LLM in current session)
        try:
            response = call_anthropic_protocol(prompt, config, max_tokens=8192)
            if verbose:
                print(f"\n[phase2]   chunk {i+1} response ({len(response)} chars):\n{response[:1000]}...\n")
            analysis = parse_yaml_block(response)
            analysis["_chunk_index"] = i + 1
            analysis["_chunk_size"] = len(chunk)

            # Save analysis to base checkpoint for phase3
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                # Load existing data
                base_data = json.load(f) if os.path.exists(f) else {}
                # Update/add chunk analysis
                if "chunk_analyses" not in base_data:
                    base_data["chunk_analyses"] = []
                base_data["chunk_analyses"].append(analysis)

                # Write back
                open(f, "w", encoding="utf-8").write(json.dumps(base_data, ensure_ascii=False, indent=2))

                n_concepts = len(analysis.get("concepts_found", []))
                n_entities = len(analysis.get("entities_found", []))
                print(f"✗ chunk {i+1}: {n_concepts} concepts, {n_entities} entities")

            except RuntimeError as e:
                print(f"❌ chunk {i+1}: {e}")
                # Save error to base checkpoint
                with open(checkpoint_path, "w", encoding="utf-8") as f:
                    base_data = json.load(f) if os.path.exists(f) else {}
                    if "chunk_analyses" not in base_data:
                        base_data["chunk_analyses"] = []
                    base_data["chunk_analyses"].append({"chunk_index": i + 1, "error": str(e), "chunk_text_length": len(chunk)})
                    open(f, "w", encoding="utf-8").write(json.dumps(base_data, ensure_ascii=False, indent=2))
                print(f"\n⏸️ Enter to continue processing chunk {i+1}...")
                input()

        # After all chunks processed, update base checkpoint
        checkpoint_data = {
            "phase": "chunked",
            "extracted_text": extracted_text,
            "extract_method": "pymupdf",
            "global_digest": global_digest,
            "chunk_analyses": analyses,
            "raw_file": str(raw_file),
            "_source_hash": hashlib.sha256(extracted_text.encode()).hexdigest(),
            "_updated_at": time.time(),
        }
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)

        print(f"[phase2] ✅ Done — {chunk_total} chunks analyzed, total {sum(len(a.get(\"concepts_found\", []))} concepts, {sum(len(a.get(\"entities_found\", []))} entities total")

