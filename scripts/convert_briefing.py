#!/usr/bin/env python3
"""Turn an exported Daily Briefing (Briefing tab + References tab, as Markdown)
into a Jekyll post for the Daily Deep Dive (3D) site.

Usage:
  python3 scripts/convert_briefing.py BRIEFING.md REFERENCES.md [--field "Technology"] [--posts _posts]

What it does:
  - reads the date from the "# Daily Briefing: <Weekday>, <Month> <D>, <YYYY>" title
  - uses the "## Deep dive: ..." heading as the post title
  - turns the "Covering <day>: ..." line into the post's summary
  - turns bracketed source numbers like [5] into clickable superscripts
  - puts the References tab (and its notes) at the bottom of the post
  - removes private claude.ai links and the "reply in this chat" line,
    and links earlier briefings to their posts on this site when they exist
Standard library only, so it runs anywhere Python 3 does.
"""
import argparse
import datetime as dt
import pathlib
import re
import sys

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}

CITE = re.compile(r"[ \t]*((?:\\\[\d{1,3}\\\])+)")
CITE_NUM = re.compile(r"\d{1,3}")
PRIVATE_LINK = re.compile(r"\[([^\]]+)\]\(https://claude\.ai/[^)]*\)")
SECTION_IDS = {
    "markets": "markets",
    "politics and world": "politics-and-world",
    "quick hits": "quick-hits",
    "spaced repetition": "spaced-repetition",
    "deep dive": "deep-dive",
}


def yaml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def slugify(s: str, limit: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    if len(s) > limit:
        s = s[:limit].rsplit("-", 1)[0]
    return s


def cites(text: str) -> str:
    """[2][3] -> one superscript '2,3' whose numbers link to the references."""
    def one(m):
        nums = CITE_NUM.findall(m.group(1))
        links = ",".join(f'<a href="#ref-{n}" title="Source {n}">{n}</a>' for n in nums)
        return f'<sup class="cite">{links}</sup>'
    return CITE.sub(one, text)


def no_liquid(text: str) -> str:
    return text.replace("{{", "&#123;&#123;").replace("{%", "&#123;%")


def parse_title_date(line: str) -> dt.date:
    m = re.search(r"(\w+) (\d{1,2}), (\d{4})", line)
    if not m or m.group(1) not in MONTHS:
        sys.exit(f"Could not read a date from the title line: {line!r}")
    return dt.date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))


def find_post(posts: pathlib.Path, day: dt.date):
    hits = sorted(posts.glob(f"{day.isoformat()}-*.md"))
    return hits[0].stem if hits else None


def convert_body(lines, posts_dir):
    out, sections = [], []
    title = None
    in_your_call = False
    i = 0
    while i < len(lines):
        line = lines[i]

        # Section headings (##)
        if line.startswith("## "):
            if in_your_call:
                out += ["", "</div>", ""]
                in_your_call = False
            heading = line[3:].strip()
            key = heading.split(":")[0].strip().lower()
            sid = SECTION_IDS.get(key, slugify(heading))
            if key == "deep dive":
                title = heading.split(":", 1)[1].strip() if ":" in heading else heading
                sections.append({"label": "Deep dive", "id": sid, "deep": True})
                out += [f"## {heading}", "{: #" + sid + " .deep-dive-head}"]
            else:
                sections.append({"label": heading.split(":")[0].strip(), "id": sid, "deep": False})
                out += [f"## {heading}", "{: #" + sid + "}"]
            i += 1
            continue

        # Your Call box
        if line.strip().lower() == "### your call":
            out += ['<div class="your-call" markdown="1">', "", line]
            in_your_call = True
            i += 1
            continue

        # Private workflow line in Your Call
        if line.startswith("Reply in this chat"):
            i += 1
            continue

        # Tables: wrap so they scroll on phones
        if line.startswith("|"):
            block = []
            while i < len(lines) and lines[i].startswith("|"):
                block.append(cites(PRIVATE_LINK.sub(r"\1", lines[i])))
                i += 1
            out += ['<div class="table-wrap" markdown="1">', ""] + block + ["", "</div>"]
            continue

        out.append(cites(PRIVATE_LINK.sub(r"\1", line)))
        i += 1

    if in_your_call:
        out += ["", "</div>"]
    return out, sections, title


REF_LINE = re.compile(r"^(\d{1,3})\.\s+(.*)$")
MD_LINK = re.compile(r"^\[(.+?)\]\((\S+?)\)\s*(?:[—-]\s*(.*))?$")


def convert_references(text: str, posts_dir: pathlib.Path):
    refs, notes, mode = [], [], None
    for line in text.splitlines():
        if line.startswith("# "):
            mode = "refs"
            continue
        if line.lower().startswith("## notes on the data"):
            mode = "notes"
            continue
        if mode == "refs":
            m = REF_LINE.match(line)
            if not m:
                continue
            num, rest = m.group(1), m.group(2).strip()
            lm = MD_LINK.match(rest)
            if lm:
                ttl, url, pub = lm.group(1), lm.group(2), (lm.group(3) or "").strip()
            else:
                ttl, url, pub = rest, None, ""
            if url and url.startswith("https://claude.ai/"):
                # Earlier briefing? Link to its post on this site if there is one.
                post = None
                if ttl.lower().startswith("daily briefing"):
                    try:
                        post = find_post(posts_dir, parse_title_date(ttl))
                    except SystemExit:
                        post = None
                if post:
                    link = f'<a href="{{% post_url {post} %}}">{ttl}</a>'
                    pub = "earlier post on this site" + (f" ({pub.split('(', 1)[1]}" if "(" in pub else "")
                elif "forecast log" in ttl.lower():
                    link, pub = ttl, "the author's running log of Your Call predictions and scores"
                else:
                    link = ttl
                    pub = pub.replace("earlier briefing", "earlier briefing, not yet on this site")
            elif url:
                link = f'<a href="{url}" rel="noopener">{ttl}</a>'
            else:
                link = ttl
            refs.append(f'<li id="ref-{num}">{link}' + (f' <span class="pub">— {pub}</span>' if pub else "") + "</li>")
        elif mode == "notes":
            notes.append(cites(PRIVATE_LINK.sub(r"\1", line)))
    return refs, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("briefing")
    ap.add_argument("references")
    ap.add_argument("--field", default="", help="Field of the deep dive, e.g. 'Technology'")
    ap.add_argument("--posts", default=str(pathlib.Path(__file__).resolve().parent.parent / "_posts"))
    args = ap.parse_args()

    posts_dir = pathlib.Path(args.posts)
    posts_dir.mkdir(parents=True, exist_ok=True)
    raw = pathlib.Path(args.briefing).read_text(encoding="utf-8").splitlines()
    ref_text = pathlib.Path(args.references).read_text(encoding="utf-8")

    title_line = next((l for l in raw if l.startswith("# ")), None)
    if not title_line:
        sys.exit("No '# Daily Briefing: ...' title line found.")
    day = parse_title_date(title_line)

    # Header block: everything before the first "## " heading.
    first_h2 = next(i for i, l in enumerate(raw) if l.startswith("## "))
    covering, summary = "", ""
    for l in raw[:first_h2]:
        m = re.match(r"^Covering ([^:]+):\s*(.+)$", l.strip())
        if m:
            covering = m.group(1).strip()
            summary = m.group(2).strip()
            summary = summary[0].upper() + summary[1:]
            if not summary.endswith("."):
                summary += "."

    body, sections, title = convert_body(raw[first_h2:], posts_dir)
    if not title:
        sys.exit("No '## Deep dive: ...' heading found.")
    refs, notes = convert_references(ref_text, posts_dir)
    sections.append({"label": "References", "id": "references", "deep": False})

    fm = ["---",
          f"title: {yaml_str(title)}",
          f"date: {day.isoformat()} 07:00:00 -0500",
          f"covering: {yaml_str(covering)}" if covering else None,
          f"summary: {yaml_str(summary)}" if summary else None,
          f"description: {yaml_str(summary)}" if summary else None,
          f"field: {yaml_str(args.field)}" if args.field else None,
          "sections:"]
    fm = [x for x in fm if x is not None]
    for s in sections:
        fm.append(f"  - {{ label: {yaml_str(s['label'])}, id: {s['id']}" + (", deep: true" if s["deep"] else "") + " }")
    fm.append("---")

    tail = ["", '<section class="references" markdown="1">', "", "## References", "{: #references}", "",
            '<ol class="refs">'] + refs + ["</ol>", ""]
    if notes:
        tail += ["### Notes on the data", ""] + notes + [""]
    tail += ["</section>", ""]

    content = "\n".join(fm) + "\n\n" + no_liquid("\n".join(body).strip()) + "\n" + "\n".join(tail)
    # A post with the same date replaces the earlier version (re-runs, corrections).
    for old in posts_dir.glob(f"{day.isoformat()}-*.md"):
        old.unlink()
    out = posts_dir / f"{day.isoformat()}-{slugify(title)}.md"
    out.write_text(content, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
