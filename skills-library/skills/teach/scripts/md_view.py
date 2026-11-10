#!/usr/bin/env python3
"""What a reader of a Markdown file actually sees, as JSON, from a real CommonMark parser.

Regex views of Markdown kept accepting decoys a renderer never shows: links in comments,
fences, code spans, indented code, raw HTML, attributes, images (core review rounds 2 to 6).
This parses with markdown-it-py (the version CI installs) and reports only rendered content:

  links     hrefs of real anchors (not images, not raw HTML)
  sections  [{heading, items, tables}] in document order; `items` are list-item texts and
            `tables` are rows of cell texts (anchors kept as [text](href)), each under the
            heading that precedes it
  text      the visible inline text of the whole document, code spans kept in backticks

Usage: python3 md_view.py < file.md   (exits 2 when markdown-it-py is unavailable)
"""
import json
import sys

try:
    from markdown_it import MarkdownIt
except ImportError:  # fail closed: no parser, no verdict
    print("markdown-it-py is required (CI installs markdown-it-py==4.2.0)", file=sys.stderr)
    sys.exit(2)


def inline_text(tok, links=False):
    """Visible text of an inline token: text and code spans, never raw HTML or images. With
    links=True, real anchors are kept as [text](href) so a cell can be checked for its link."""
    out, hrefs = [], []
    for c in tok.children or []:
        if links and c.type == "link_open":
            hrefs.append(c.attrGet("href") or "")
            out.append("[")
        elif links and c.type == "link_close":
            out.append("](" + (hrefs.pop() if hrefs else "") + ")")
        elif c.type == "text":
            out.append(c.content)
        elif c.type == "code_inline":
            out.append("`" + c.content + "`")
        elif c.type in ("softbreak", "hardbreak"):
            out.append("\n")
    return "".join(out)


def view(md):
    if md.startswith("---\n"):  # YAML frontmatter is metadata, not rendered content
        end = md.find("\n---\n", 4)
        md = md[end + 5:] if end >= 0 else md
    tokens = MarkdownIt("commonmark").enable("table").parse(md)
    links, texts = [], []
    sections = [{"heading": "", "items": [], "tables": []}]
    depth_item = 0
    row, rows, in_table = None, None, False
    for i, t in enumerate(tokens):
        if t.type == "heading_open":
            sections.append({"heading": inline_text(tokens[i + 1]).strip(), "items": [], "tables": []})
        elif t.type == "list_item_open":
            depth_item += 1
        elif t.type == "list_item_close":
            depth_item -= 1
        elif t.type == "table_open":
            in_table, rows = True, []
        elif t.type == "table_close":
            in_table = False
            sections[-1]["tables"].append(rows)
        elif t.type == "tr_open":
            row = []
        elif t.type == "tr_close":
            rows.append(row)
        elif t.type == "inline":
            text = inline_text(t)
            texts.append(text)
            for c in t.children or []:
                if c.type == "link_open":
                    links.append(c.attrGet("href"))
            if in_table and row is not None and tokens[i - 1].type in ("th_open", "td_open"):
                row.append(inline_text(t, links=True).strip())
            elif depth_item and tokens[i - 1].type == "paragraph_open":
                sections[-1]["items"].append(text.strip())
    return {"links": links, "sections": sections, "text": "\n".join(texts)}


if __name__ == "__main__":
    print(json.dumps(view(sys.stdin.read())))
