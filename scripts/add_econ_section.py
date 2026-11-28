#!/usr/bin/env python3
"""Fill the 8:30 a.m. economic-data section of an already-published briefing post.

Usage:
  python3 scripts/add_econ_section.py POST.md ECON.md [--dry-run]

POST.md is a post in _posts/ made by convert_briefing.py. The morning briefing
leaves a placeholder in its Markets section: a "### Economic data ..." heading
and a line saying the section fills in after the release. This script replaces
that heading and everything after it, up to the next "## " heading, with the
new section. If there is no placeholder, the section goes just before
"## Politics and world".

ECON.md is plain Markdown in three parts:

  ### Economic data (8:30 a.m. ET): <short factual headline>
  <body: bullets or short paragraphs; cite sources as [e1], [e2] ...>

  ## References
  e1. [Title](https://specific.link/to/the/release) — Publisher, date
  e2. ...

  ## Notes on the data
  - one line per note (how figures were computed, what was left out)

The e-numbers are renumbered to follow the post's last reference, the
references are appended to the post's list, and the notes are appended to its
"Notes on the data". Standard library only.
"""
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from convert_briefing import cites, no_liquid  # noqa: E402

E_CITE = re.compile(r"\\?\[e(\d{1,2})\\?\]")
E_REF = re.compile(r"^e(\d{1,2})\.\s+(.*)$")
MD_LINK = re.compile(r"^\[(.+?)\]\((\S+?)\)\s*(?:[—-]\s*(.*))?$")
MARKER_RE = re.compile(r"<!-- econ-section refs=(\d+)-(\d+) -->")
NOTES_START, NOTES_END = "<!-- econ-notes -->", "<!-- /econ-notes -->"


def parse_econ(text):
    body, refs, notes, mode = [], [], [], "body"
    for line in text.splitlines():
        low = line.strip().lower()
        if low == "## references":
            mode = "refs"
            continue
        if low == "## notes on the data":
            mode = "notes"
            continue
        if mode == "body":
            body.append(line)
        elif mode == "refs":
            m = E_REF.match(line.strip())
            if m:
                refs.append((m.group(1), m.group(2).strip()))
        elif line.strip():
            notes.append(line.rstrip())
    while body and not body[-1].strip():
        body.pop()
    if not body or not body[0].startswith("### Economic data"):
        sys.exit('ECON.md must start with a "### Economic data ..." heading')
    if not refs:
        sys.exit("ECON.md has no references (lines like 'e1. [Title](url) — Publisher')")
    return body, refs, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("post")
    ap.add_argument("econ")
    ap.add_argument("--dry-run", action="store_true", help="print the result instead of writing it")
    args = ap.parse_args()

    post_path = pathlib.Path(args.post)
    post = post_path.read_text(encoding="utf-8")
    body, refs, notes = parse_econ(pathlib.Path(args.econ).read_text(encoding="utf-8"))

    prev = MARKER_RE.search(post)
    if prev:
        # Re-run: drop the references and notes this script added last time.
        lo, hi = int(prev.group(1)), int(prev.group(2))
        for n in range(lo, hi + 1):
            post = re.sub(rf'<li id="ref-{n}">.*?</li>\n', "", post)
        post = re.sub(re.escape(NOTES_START) + r".*?" + re.escape(NOTES_END) + r"\n*", "", post, flags=re.S)
        print("Note: replacing an economic-data section that was already filled.", file=sys.stderr)
    existing = [int(n) for n in re.findall(r'<li id="ref-(\d+)"', post)]
    if not existing:
        sys.exit("No references found in the post; was it made by convert_briefing.py?")
    start = max(existing) + 1
    numbers = {e: str(start + i) for i, (e, _) in enumerate(refs)}

    used = set(E_CITE.findall("\n".join(body + notes)))
    missing = sorted(used - set(numbers), key=int)
    if missing:
        sys.exit(f"Cited but not in ECON.md references: {', '.join('e' + m for m in missing)}")

    def renumber(line):
        return E_CITE.sub(lambda m: f"\\[{numbers[m.group(1)]}\\]", line)

    marker = f"<!-- econ-section refs={start}-{start + len(refs) - 1} -->"
    section = [body[0], marker, ""] + [no_liquid(cites(renumber(l))) for l in body[1:]] + [""]

    lines = post.split("\n")
    head_i = next((i for i, l in enumerate(lines) if l.startswith("### Economic data")), None)
    if head_i is not None:
        end_i = next((i for i in range(head_i + 1, len(lines)) if lines[i].startswith("## ")), None)
        if end_i is None:
            sys.exit("Could not find the heading after the economic-data placeholder")
        lines[head_i:end_i] = section
    else:
        pol = next((i for i, l in enumerate(lines) if l.startswith("## Politics and world")), None)
        if pol is None:
            sys.exit('No placeholder and no "## Politics and world" heading to insert before')
        lines[pol:pol] = section

    out = "\n".join(lines)

    items = []
    for e, rest in refs:
        lm = MD_LINK.match(rest)
        if not lm:
            sys.exit(f"Reference e{e} must be '[Title](url) — Publisher': {rest!r}")
        ttl, url, pub = lm.group(1), lm.group(2), (lm.group(3) or "").strip()
        if url.startswith("https://claude.ai/"):
            sys.exit(f"Reference e{e} links to claude.ai; public posts must not")
        item = f'<li id="ref-{numbers[e]}"><a href="{url}" rel="noopener">{ttl}</a>'
        item += (f' <span class="pub">— {pub}</span>' if pub else "") + "</li>"
        items.append(item)
    ol_end = out.find("</ol>", out.find('<ol class="refs">'))
    if ol_end < 0:
        sys.exit("Could not find the post's references list")
    out = out[:ol_end] + "\n".join(items) + "\n" + out[ol_end:]

    if notes:
        sec_end = out.rfind("</section>")
        if sec_end < 0:
            sys.exit("Could not find the end of the references section")
        block = "\n".join(no_liquid(cites(renumber(n))) for n in notes)
        out = (out[:sec_end].rstrip("\n") + "\n\n" + NOTES_START + "\n" + block + "\n" + NOTES_END
               + "\n\n" + out[sec_end:])

    if args.dry_run:
        print(out)
    else:
        post_path.write_text(out, encoding="utf-8")
        print(post_path)


if __name__ == "__main__":
    main()
