"""Check the Markdown documents: links, image paths, anchors, footnotes, heading levels and punctuation.

Run from the repository root:

    uv run docs/scripts/check_docs.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(".").resolve()
SKIP = {".git", "build", "tmp"}
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def slug(heading):
    """GitHub anchor for a heading, before duplicates are numbered."""
    heading = heading.lower().replace("`", "").replace("&nbsp;", "")
    heading = re.sub(r"[^a-z0-9 _-]", "", heading)
    return heading.strip().replace(" ", "-")


def anchors(path):
    """Anchors of a file. GitHub appends -1, -2, ... to repeated headings."""
    text = re.sub(r"(?s)```.*?```", "", path.read_text())
    seen, result = {}, {}
    for heading in re.findall(r"(?m)^#+ (.*)$", text):
        base = slug(heading)
        count = seen.get(base, 0)
        seen[base] = count + 1
        result[base if count == 0 else "%s-%d" % (base, count)] = count > 0
    return result


problems = 0
files = [f for f in sorted(ROOT.rglob("*.md")) if not SKIP & set(f.relative_to(ROOT).parts)]
for md in files:
    rel = md.relative_to(ROOT)
    text = md.read_text()
    prose = re.sub(r"(?s)```.*?```", "", text)

    def report(kind, detail):
        global problems
        problems += 1
        print("%-8s %s: %s" % (kind, rel, detail))

    if re.search("[–—]", text):
        report("DASH", "en or em dash")
    if "**" in prose:
        report("BOLD", "bold text")
    levels = [len(m.group(1)) for m in re.finditer(r"(?m)^(#+) ", prose)]
    for before, after in zip(levels, levels[1:]):
        if after > before + 1:
            report("HEADING", "level %d followed by level %d" % (before, after))
    targets = re.findall(r"\]\(([^)\s]+)\)", prose) + re.findall(r'src="([^"]+)"', prose)
    for target in targets:
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        path, _, anchor = target.partition("#")
        dest = (md.parent / path) if path else md
        if not dest.exists():
            report("BROKEN", target)
        elif anchor and dest.is_file() and dest.suffix == ".md":
            found = anchors(dest)
            if anchor not in found:
                report("ANCHOR", target)
            elif found[anchor]:
                report("FRAGILE", "%s depends on the order of repeated headings" % target)
    for line in prose.split("\n"):
        if line.startswith("|") and re.search(r"\d ×|× \d", line):
            report("NBSP", line[:70])
        # A coordinate is a pair of exactly two numbers, not part of a longer list.
        if line.startswith("|") and re.search(r"(?<!, )(?<![\w./])\d+(\.\d+)?, \d+(\.\d+)?(?![\w./]|, \d)", line):
            report("NBSP", line[:70])
    for m in re.finditer(r"\[[^\]]* README\]", prose):
        report("NBSP", m.group(0))
    defined = set(re.findall(r"(?m)^\[\^([^\]]+)\]:", prose))
    used = set(re.findall(r"\[\^([^\]]+)\](?!:)", prose))
    for label in sorted(used - defined):
        report("FOOTNOTE", "[^%s] used but not defined" % label)
    for label in sorted(defined - used):
        report("FOOTNOTE", "[^%s] defined but not used" % label)
    for m in re.finditer(r"\b(?:%s) \d{1,2}, \d{4}\b|\b\d{1,2}/\d{1,2}/\d{4}\b" % MONTHS, prose):
        report("DATE", "%s is neither ISO nor day-first" % m.group(0))

print("checked %d files, %d problems" % (len(files), problems))
sys.exit(1 if problems else 0)
