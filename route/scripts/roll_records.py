#!/usr/bin/env python3
"""Deterministic record roll tool for model-routing bookkeeping.

Moves overflow or completed entries from a hot tracking file (e.g. PROGRESS.md, TASK.md)
to an archive file (e.g. PROGRESS_ARCHIVE.md, TASK_ARCHIVE.md).

Safety guarantees:
1. Insert-before-delete: writes to the archive first and verifies the headings landed
   before removing anything from the hot file.
2. Preserves newest-first ordering (or oldest-first if requested).
3. Verifies entry counts before and after surgery.

Usage:
  python3 roll_records.py --hot docs/agent/PROGRESS.md --archive docs/agent/PROGRESS_ARCHIVE.md --keep 2
  python3 roll_records.py --hot docs/agent/TASK.md --archive docs/agent/TASK_ARCHIVE.md --keep 0 --heading-pattern "^### "
"""
import argparse
import os
import re
import sys


def find_entries(content: str, heading_pattern: str):
    """Split markdown content into (header_preamble, list_of_entries).
    Each entry is a dict: {'heading': str, 'raw': str}
    """
    heading_re = re.compile(heading_pattern, re.M)
    matches = list(heading_re.finditer(content))
    if not matches:
        return content, []

    first_entry_pos = matches[0].start()
    
    # If the first entry is preceded by a horizontal rule ("---\n\n"), include that separator boundary
    sep_match = re.search(r"\n---\s*\n\s*$", content[:first_entry_pos])
    if sep_match:
        header = content[:sep_match.start()].rstrip() + "\n"
    else:
        header = content[:first_entry_pos].rstrip() + "\n"

    entries = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        
        # Check if next entry is preceded by "---" separator
        entry_text = content[start:end]
        sep_idx = entry_text.rfind("\n---")
        if i + 1 < len(matches) and sep_idx != -1:
            entry_text = entry_text[:sep_idx]
            
        heading_line = content[m.start():content.find("\n", m.start()) if content.find("\n", m.start()) != -1 else m.end()].strip()
        entries.append({
            "heading": heading_line,
            "raw": entry_text.strip(),
        })

    return header, entries


def roll_records(hot_path: str, archive_path: str, keep: int = 2,
                 heading_pattern: str = r"^(?:## 📅 Log:|### )",
                 mode: str = "prepend", dry_run: bool = False) -> int:
    if not os.path.exists(hot_path):
        print(f"[roll_records] Error: hot file {hot_path} not found.", file=sys.stderr)
        return 1

    with open(hot_path, "r", encoding="utf-8") as fh:
        hot_content = fh.read()

    hot_header, entries = find_entries(hot_content, heading_pattern)
    total_entries = len(entries)

    if total_entries <= keep:
        print(f"[roll_records] Nothing to roll. Hot file has {total_entries} entries (keep={keep}).")
        return 0

    to_keep = entries[:keep]
    to_roll = entries[keep:]
    roll_count = len(to_roll)

    print(f"[roll_records] Rolling {roll_count} entries from {hot_path} to {archive_path} (keeping {keep}).")

    archive_content = ""
    if os.path.exists(archive_path):
        with open(archive_path, "r", encoding="utf-8") as fh:
            archive_content = fh.read()

    arch_header, arch_entries = find_entries(archive_content, heading_pattern)
    if not arch_header.strip():
        # Derive a default archive header if missing
        basename = os.path.basename(hot_path).replace(".md", "")
        arch_header = f"# {basename.capitalize()} archive\n\nOlder {basename.lower()} entries, prepended from `{os.path.basename(hot_path)}`.\n"

    # Format the block of entries to roll
    # Use separator "---" if entries have "Log:" or if hot file had "---"
    has_separators = "\n---" in hot_content or "## 📅 Log:" in heading_pattern

    if has_separators:
        formatted_roll = "\n\n---\n\n".join(e["raw"] for e in to_roll)
    else:
        formatted_roll = "\n\n".join(e["raw"] for e in to_roll)

    # Build new archive content
    if mode == "prepend":
        if arch_entries:
            if has_separators:
                existing_arch_body = "\n\n---\n\n".join(e["raw"] for e in arch_entries)
                new_archive = f"{arch_header.rstrip()}\n\n---\n\n{formatted_roll}\n\n---\n\n{existing_arch_body}\n"
            else:
                existing_arch_body = "\n\n".join(e["raw"] for e in arch_entries)
                new_archive = f"{arch_header.rstrip()}\n\n{formatted_roll}\n\n{existing_arch_body}\n"
        else:
            if has_separators:
                new_archive = f"{arch_header.rstrip()}\n\n---\n\n{formatted_roll}\n"
            else:
                new_archive = f"{arch_header.rstrip()}\n\n{formatted_roll}\n"
    else:  # append
        if arch_entries:
            if has_separators:
                existing_arch_body = "\n\n---\n\n".join(e["raw"] for e in arch_entries)
                new_archive = f"{arch_header.rstrip()}\n\n---\n\n{existing_arch_body}\n\n---\n\n{formatted_roll}\n"
            else:
                existing_arch_body = "\n\n".join(e["raw"] for e in arch_entries)
                new_archive = f"{arch_header.rstrip()}\n\n{existing_arch_body}\n\n{formatted_roll}\n"
        else:
            if has_separators:
                new_archive = f"{arch_header.rstrip()}\n\n---\n\n{formatted_roll}\n"
            else:
                new_archive = f"{arch_header.rstrip()}\n\n{formatted_roll}\n"

    # Build new hot content
    if to_keep:
        if has_separators:
            kept_body = "\n\n---\n\n".join(e["raw"] for e in to_keep)
            new_hot = f"{hot_header.rstrip()}\n\n---\n\n{kept_body}\n"
        else:
            kept_body = "\n\n".join(e["raw"] for e in to_keep)
            new_hot = f"{hot_header.rstrip()}\n\n{kept_body}\n"
    else:
        new_hot = f"{hot_header.rstrip()}\n"

    if dry_run:
        print("[roll_records] [DRY RUN] Would write archive and update hot file.")
        for e in to_roll:
            print(f"  - Would roll: {e['heading']}")
        return 0

    # Step 1: Write archive FIRST
    os.makedirs(os.path.dirname(os.path.abspath(archive_path)), exist_ok=True)
    with open(archive_path, "w", encoding="utf-8") as fh:
        fh.write(new_archive)

    # Step 2: Verify archive landed correctly on disk
    with open(archive_path, "r", encoding="utf-8") as fh:
        verify_content = fh.read()

    for e in to_roll:
        if e["heading"] not in verify_content:
            print(f"[roll_records] Verification FAILED: heading '{e['heading']}' missing from archive! Aborting without modifying hot file.", file=sys.stderr)
            return 1

    _, verified_arch_entries = find_entries(verify_content, heading_pattern)
    expected_arch_total = len(arch_entries) + roll_count
    if len(verified_arch_entries) != expected_arch_total:
        print(f"[roll_records] Verification FAILED: expected {expected_arch_total} entries in archive, got {len(verified_arch_entries)}. Aborting hot file update.", file=sys.stderr)
        return 1

    # Step 3: Write hot file LAST
    with open(hot_path, "w", encoding="utf-8") as fh:
        fh.write(new_hot)

    # Verify hot file
    with open(hot_path, "r", encoding="utf-8") as fh:
        verify_hot_content = fh.read()
    _, verified_hot_entries = find_entries(verify_hot_content, heading_pattern)
    if len(verified_hot_entries) != keep:
        print(f"[roll_records] Warning: hot file has {len(verified_hot_entries)} entries, expected {keep}.", file=sys.stderr)

    print(f"[roll_records] SUCCESS: Rolled {roll_count} entries. Archive has {len(verified_arch_entries)} entries; hot file keeps {len(verified_hot_entries)} entries.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Deterministic record rolling tool with insert-before-delete safety.")
    parser.add_argument("--hot", "-H", required=True, help="Path to hot markdown tracking file")
    parser.add_argument("--archive", "-A", required=True, help="Path to archive markdown file")
    parser.add_argument("--keep", "-k", type=int, default=2, help="Number of newest entries to keep in hot file (default: 2)")
    parser.add_argument("--heading-pattern", "-p", default=r"^(?:## 📅 Log:|### )", help="Regex pattern for entry headings")
    parser.add_argument("--mode", choices=["prepend", "append"], default="prepend", help="Roll ordering into archive (default: prepend)")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run without touching files")

    args = parser.parse_args()
    rc = roll_records(
        hot_path=args.hot,
        archive_path=args.archive,
        keep=args.keep,
        heading_pattern=args.heading_pattern,
        mode=args.mode,
        dry_run=args.dry_run,
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
