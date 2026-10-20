"""Generate docs/roadmap.html from plan.md.

plan.md is the single source of truth; this page is a picture of it. Run after
every change to plan.md:  python scripts/build_roadmap.py
tests/test_roadmap.py fails if the committed page is out of date.
"""

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STATUSES = {
    "✅": "done",
    "🔨": "in_progress",
    "⏭": "next",
    "⬜": "todo",
    "🔬": "research",
}
STATUS_LABELS = {
    "done": "Done",
    "in_progress": "In progress",
    "next": "Next",
    "todo": "Not started",
    "research": "Needs research",
}
SOURCE_LABELS = {
    "R": "Research",
    "Y": "Your decision",
    "S": "Coach spec",
    "A": "Assumption",
}


# ---------------------------------------------------------------- parsing


def _sections(text, level):
    """Split text on headings of the given level: [(heading, body), ...]."""
    marker = "#" * level + " "
    sections, heading, body = [], None, []
    for line in text.splitlines():
        if line.startswith(marker):
            if heading is not None:
                sections.append((heading, "\n".join(body)))
            heading, body = line[len(marker):].strip(), []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(body)))
    return sections


def _section(text, name):
    for heading, body in _sections(text, 2):
        if name in heading:
            return body
    raise ValueError(f"plan.md has no section named {name!r}")


def _table(body):
    """Rows of the first Markdown table in body, header and separator skipped."""
    rows = []
    in_table = False
    for line in body.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not in_table:
                in_table = True
                continue
            if all(set(c) <= set("-: ") for c in cells):
                continue
            rows.append(cells)
        elif in_table:
            break
    return rows


def _status(cell):
    key = cell.replace("️", "").strip()
    if key not in STATUSES:
        raise ValueError(f"unknown status {cell!r} in plan.md — use one of {' '.join(STATUSES)}")
    return STATUSES[key]


def _summary(body):
    lines, collecting = [], False
    for line in body.splitlines():
        stripped = line.strip()
        if not collecting and stripped.startswith("_"):
            collecting = True
        if collecting:
            lines.append(stripped)
            if stripped.endswith("_"):
                break
    return " ".join(lines).strip("_").strip()


def parse_plan(text):
    updated = re.search(r"Last update: (\d{4}-\d{2}-\d{2})", text)

    milestones = []
    for heading, body in _sections(_section(text, "Roadmap"), 3):
        match = re.match(r"(M\d+)\s+—\s+(.+)", heading)
        if not match:
            continue
        milestones.append(
            {
                "id": match.group(1),
                "title": match.group(2).strip(),
                "summary": _summary(body),
                "items": [
                    {"status": _status(row[0]), "feature": row[1], "notes": row[2] if len(row) > 2 else ""}
                    for row in _table(body)
                ],
            }
        )

    rules = []
    for row in _table(_section(text, "Rules the app uses")):
        source = row[2].replace("**", "")
        tag = re.search(r"\[(R|Y|S|A)\]", source)
        if not tag:
            raise ValueError(f"rule {row[0]!r} has no [R]/[Y]/[S]/[A] source tag")
        rules.append(
            {
                "rule": row[0],
                "used_in": row[1],
                "tag": tag.group(1),
                "source": source.replace(tag.group(0), "", 1).strip(),
            }
        )

    research = [
        {"status": _status(row[0]), "topic": row[1], "decides": row[2]}
        for row in _table(_section(text, "Research"))
    ]
    decisions = [
        {"status": _status(row[0]), "decision": row[1], "needed_for": row[2]}
        for row in _table(_section(text, "Decisions needed"))
    ]
    waiting = [
        {"status": _status(row[0]), "item": row[1], "who": row[2]}
        for row in _table(_section(text, "Waiting on"))
    ]

    return {
        "updated": updated.group(1) if updated else "",
        "milestones": milestones,
        "rules": rules,
        "research": research,
        "decisions": decisions,
        "waiting": waiting,
    }


def progress(milestone):
    done = sum(1 for item in milestone["items"] if item["status"] == "done")
    return done, len(milestone["items"])


# ---------------------------------------------------------------- rendering


def _inline(text):
    """Escape, then allow the two bits of Markdown plan.md cells use."""
    out = html.escape(text, quote=True)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    return out


def _chip(status):
    return f'<span class="chip st-{status}">{STATUS_LABELS[status]}</span>'


def _milestone(milestone):
    done, total = progress(milestone)
    percent = round(done / total * 100) if total else 0
    items = "\n".join(
        f"""        <li class="item st-{item['status']}">
          {_chip(item['status'])}
          <span class="feature">{_inline(item['feature'])}</span>
          {f'<span class="notes">{_inline(item["notes"])}</span>' if item['notes'] else ''}
        </li>"""
        for item in milestone["items"]
    )
    return f"""    <section class="milestone">
      <header>
        <span class="mid">{milestone['id']}</span>
        <h2>{_inline(milestone['title'])}</h2>
        <p class="summary">{_inline(milestone['summary'])}</p>
        <div class="progress"><span style="width:{percent}%"></span></div>
        <span class="count">{done} / {total} done</span>
      </header>
      <ul>
{items}
      </ul>
    </section>"""


def _rows(entries, cells):
    return "\n".join("        <tr>" + "".join(cells(e)) + "</tr>" for e in entries)


def render(plan):
    milestones = "\n".join(_milestone(m) for m in plan["milestones"])
    waiting = _rows(
        plan["waiting"],
        lambda w: [f"<td>{_chip(w['status'])}</td>", f"<td>{_inline(w['item'])}</td>", f"<td class=\"muted\">{_inline(w['who'])}</td>"],
    )
    decisions = _rows(
        plan["decisions"],
        lambda d: [f"<td>{_chip(d['status'])}</td>", f"<td>{_inline(d['decision'])}</td>", f"<td class=\"muted\">{_inline(d['needed_for'])}</td>"],
    )
    research = _rows(
        plan["research"],
        lambda r: [f"<td>{_chip(r['status'])}</td>", f"<td>{_inline(r['topic'])}</td>", f"<td class=\"muted\">{_inline(r['decides'])}</td>"],
    )
    rules = _rows(
        plan["rules"],
        lambda r: [
            f"<td>{_inline(r['rule'])}</td>",
            f"<td class=\"muted\">{_inline(r['used_in'])}</td>",
            f"<td><span class=\"badge src-{r['tag']}\">{SOURCE_LABELS[r['tag']]}</span> {_inline(r['source'])}</td>",
        ],
    )
    legend = " ".join(f'<span class="badge src-{k}">{v}</span>' for k, v in SOURCE_LABELS.items())
    statuses = " ".join(_chip(s) for s in STATUS_LABELS)

    return f"""<!doctype html>
<!-- Generated from plan.md by scripts/build_roadmap.py. Do not edit by hand. -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Distrava Roadmap</title>
<style>
  @font-face {{ font-family: "Inter"; font-weight: 400 800; src: url("../app/static/fonts/Inter-var.woff2") format("woff2"); }}
  @font-face {{ font-family: "JetBrains Mono"; font-weight: 400 700; src: url("../app/static/fonts/JetBrainsMono-var.woff2") format("woff2"); }}
  :root {{
    --bg: #0b0b0f; --surface: #16161c; --surface-2: #1e1e26; --input: #101015;
    --border: #22222a; --border-strong: #2c2c36; --divider: #17171d;
    --accent: #c4f82a; --text: #ececef; --text-2: #9c9ca6; --muted: #5e5e68;
    --blue: #7fb2e8; --amber: #c9a46b;
    --mono: "JetBrains Mono", ui-monospace, monospace; --sans: "Inter", system-ui, sans-serif;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--sans); -webkit-font-smoothing: antialiased; padding: 40px 32px 80px; }}
  main {{ max-width: 1320px; margin: 0 auto; }}
  .top {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; flex-wrap: wrap; padding-bottom: 28px; border-bottom: 1px solid var(--border); margin-bottom: 28px; }}
  .wordmark {{ font-weight: 800; font-size: 28px; letter-spacing: -0.03em; }}
  .wordmark span {{ color: var(--accent); }}
  .top h1 {{ font-weight: 600; font-size: 15px; color: var(--text-2); margin-top: 8px; }}
  .meta {{ font-family: var(--mono); font-size: 12px; color: var(--muted); text-align: right; line-height: 1.8; }}
  .legend {{ display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; margin-top: 6px; }}
  .milestones {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 36px; }}
  .milestone {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; display: flex; flex-direction: column; overflow: hidden; }}
  .milestone header {{ padding: 18px 18px 14px; border-bottom: 1px solid var(--divider); }}
  .mid {{ font-family: var(--mono); font-size: 11px; letter-spacing: 0.14em; color: var(--accent); }}
  .milestone h2 {{ font-size: 18px; font-weight: 600; letter-spacing: -0.02em; margin-top: 6px; }}
  .summary {{ font-size: 13px; color: var(--text-2); line-height: 1.5; margin-top: 6px; min-height: 40px; }}
  .progress {{ height: 6px; background: var(--surface-2); border-radius: 3px; overflow: hidden; margin-top: 12px; }}
  .progress span {{ display: block; height: 100%; background: var(--accent); }}
  .count {{ display: block; font-family: var(--mono); font-size: 11px; color: var(--muted); margin-top: 6px; }}
  .milestone ul {{ list-style: none; padding: 10px; display: flex; flex-direction: column; gap: 8px; }}
  .item {{ background: var(--input); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; }}
  .item.st-done {{ opacity: 0.6; }}
  .item.st-next, .item.st-in_progress {{ border-color: rgba(196, 248, 42, 0.45); }}
  .feature {{ font-size: 13px; line-height: 1.4; }}
  .notes {{ font-family: var(--mono); font-size: 10.5px; color: var(--muted); line-height: 1.5; }}
  .chip {{ align-self: flex-start; font-family: var(--mono); font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase; border-radius: 7px; padding: 3px 7px; white-space: nowrap; }}
  .chip.st-done {{ color: var(--accent); background: rgba(196, 248, 42, 0.12); }}
  .chip.st-in_progress {{ color: var(--bg); background: var(--accent); }}
  .chip.st-next {{ color: var(--accent); border: 1px solid rgba(196, 248, 42, 0.5); }}
  .chip.st-research {{ color: var(--blue); border: 1px solid rgba(127, 178, 232, 0.45); }}
  .chip.st-todo {{ color: var(--muted); border: 1px solid var(--border-strong); }}
  .panels {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }}
  .panel {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }}
  .panel.spaced {{ margin-bottom: 14px; }}
  .panel h3 {{ font-size: 16px; font-weight: 600; padding: 16px 18px; border-bottom: 1px solid var(--divider); }}
  .panel h3 small {{ font-family: var(--mono); font-size: 11px; font-weight: 400; color: var(--muted); margin-left: 8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  td {{ padding: 10px 18px; border-bottom: 1px solid var(--divider); vertical-align: top; line-height: 1.5; }}
  tr:last-child td {{ border-bottom: none; }}
  td.muted {{ color: var(--text-2); }}
  code {{ font-family: var(--mono); font-size: 12px; color: var(--text-2); background: var(--surface-2); border-radius: 4px; padding: 1px 4px; }}
  .badge {{ display: inline-block; font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase; border-radius: 7px; padding: 3px 7px; margin-right: 6px; white-space: nowrap; }}
  .src-R {{ color: var(--bg); background: var(--accent); }}
  .src-Y {{ color: var(--blue); border: 1px solid rgba(127, 178, 232, 0.5); }}
  .src-S {{ color: var(--text-2); background: var(--surface-2); }}
  .src-A {{ color: var(--amber); border: 1px solid rgba(201, 164, 107, 0.55); }}
  footer {{ font-family: var(--mono); font-size: 11px; color: var(--muted); margin-top: 28px; }}
  @media (max-width: 1100px) {{ .milestones {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} .panels {{ grid-template-columns: 1fr; }} }}
  @media (max-width: 640px) {{ body {{ padding: 24px 16px 60px; }} .milestones {{ grid-template-columns: 1fr; }} .meta {{ text-align: left; }} .legend {{ justify-content: flex-start; }} td {{ padding: 10px 12px; }} }}
</style>
</head>
<body>
<main>
  <div class="top">
    <div>
      <div class="wordmark">D<span>I</span>STRAVA</div>
      <h1>Roadmap · M1 → M2 → M3 → M4</h1>
    </div>
    <div class="meta">
      Updated {html.escape(plan['updated'])} · from plan.md
      <div class="legend">{statuses}</div>
      <div class="legend">{legend}</div>
    </div>
  </div>

  <div class="milestones">
{milestones}
  </div>

  <div class="panels">
    <section class="panel">
      <h3>Waiting on</h3>
      <table>
{waiting}
      </table>
    </section>
    <section class="panel">
      <h3>Decisions needed <small>asked when their milestone starts</small></h3>
      <table>
{decisions}
      </table>
    </section>
  </div>

  <section class="panel spaced">
    <h3>Research <small>research/training-rules.md</small></h3>
    <table>
{research}
    </table>
  </section>

  <section class="panel">
    <h3>Rules the app uses, and where they come from</h3>
    <table>
{rules}
    </table>
  </section>

  <footer>Generated from plan.md by scripts/build_roadmap.py — edit plan.md, then run the script.</footer>
</main>
</body>
</html>
"""


def main():
    plan = parse_plan((ROOT / "plan.md").read_text())
    out = ROOT / "docs" / "roadmap.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(render(plan))
    for milestone in plan["milestones"]:
        done, total = progress(milestone)
        print(f"{milestone['id']} {milestone['title']}: {done}/{total} done")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
