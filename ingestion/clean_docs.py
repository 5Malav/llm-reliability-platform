"""
Clean Supabase MDX docs into simple JSON files.

For each .mdx file:
  0. Strip <$...> tags first (before masking, so they can't hide in code)
  1. Protect code blocks (so cleaning never touches them)
  2. Pull out frontmatter (title, description)
  3. Strip MDX component tags
  4. Restore code blocks
  5. Skip near-empty files
  6. Save as JSON

Run:  python ingestion/clean_docs.py
"""

import re
import json
from pathlib import Path

# --- Folders ---
RAW_DIR = Path("ingestion/data/raw/supabase-docs")
OUT_DIR = Path("ingestion/data/processed")

MIN_WORDS = 30  # files with less real content than this get skipped (nav-only pages)


def extract_frontmatter(text):
    """Split the --- frontmatter block from the body. Return (metadata_dict, body)."""
    metadata = {}

    # Frontmatter is a --- block at the very top
    if text.startswith("---"):
        parts = text.split("---", 2)  # ["", frontmatter, body]
        if len(parts) == 3:
            frontmatter, body = parts[1], parts[2]
            # Grab title and description with simple line matching
            for line in frontmatter.splitlines():
                if line.strip().startswith("title:"):
                    metadata["title"] = line.split("title:", 1)[1].strip().strip("'\"")
                if line.strip().startswith("description:"):
                    metadata["description"] = line.split("description:", 1)[1].strip().strip("'\"")
            return metadata, body

    return metadata, text  # no frontmatter found


def clean_body(text):
    """Strip MDX component tags. Code blocks are already masked, so this is safe."""

    # Remove standard component tags: <Tabs ...>, </Tabs>, <TabPanel>, <ContentListings/>
    # This matches any <...> that starts with a capital letter (components are capitalized)
    text = re.sub(r"</?[A-Z][^>]*>", "", text)

    # Collapse 3+ blank lines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def process_file(path):
    """Clean one MDX file. Return a dict, or None if too short."""
    raw = path.read_text(encoding="utf-8")

    ## 0. Strip ALL MDX tags BEFORE masking, so they can't get swallowed
    #    into adjacent code blocks (see INC-001). Order matters: strip-then-mask.
    raw = re.sub(r"</?\$[^>]*>", "", raw)        # <$Show>, <$Partial>
    raw = re.sub(r"</?[A-Z][^>]*>", "", raw, flags=re.DOTALL)  # <Tabs>, <TabPanel>, etc. (DOTALL = multi-line tags)

    # 1. MASK code blocks: pull them out, leave a placeholder
    code_blocks = []
    def stash(match):
        code_blocks.append(match.group(0))
        return f"__CODE_BLOCK_{len(code_blocks) - 1}__"
    masked = re.sub(r"```.*?```", stash, raw, flags=re.DOTALL)

    # 2. Frontmatter
    metadata, body = extract_frontmatter(masked)

    # 3. Strip components
    body = clean_body(body)

    # 4. RESTORE code blocks
    for i, block in enumerate(code_blocks):
        body = body.replace(f"__CODE_BLOCK_{i}__", block)

    # 5. Skip near-empty files
    if len(body.split()) < MIN_WORDS:
        return None

    # 6. Build the record
    source_path = str(path.relative_to(RAW_DIR))
    return {
        "id": path.stem,
        "title": metadata.get("title", path.stem),
        "description": metadata.get("description", ""),
        "source_path": source_path,
        "content": body,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    mdx_files = list(RAW_DIR.rglob("*.mdx"))
    processed = 0
    skipped = 0

    for path in mdx_files:
        record = process_file(path)
        if record is None:
            skipped += 1
            continue

        # Save as JSON, using the source path to avoid name clashes
        safe_name = record["source_path"].replace("/", "__").replace(".mdx", ".json")
        (OUT_DIR / safe_name).write_text(json.dumps(record, indent=2), encoding="utf-8")
        processed += 1

    print("\n--- Cleaning complete ---")
    print(f"Total .mdx files:  {len(mdx_files)}")
    print(f"Processed:         {processed}")
    print(f"Skipped (empty):   {skipped}")


if __name__ == "__main__":
    main()