"""Extract meaningful documentation changes without HTML navigation noise."""
import re
from difflib import SequenceMatcher
from html.parser import HTMLParser


class _DocumentText(HTMLParser):
    """Separate HTML paragraphs so unchanged site chrome cannot flag a release."""

    _hidden = {"script", "style", "nav", "header", "footer", "noscript"}
    _blocks = {"p", "div", "li", "h1", "h2", "h3", "h4", "pre", "tr", "br"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._hidden:
            self.hidden.append(tag)
        if not self.hidden and tag in self._blocks:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
        elif tag in self._blocks:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _document_lines(content: str) -> list[str]:
    if re.search(r"<(?:!doctype|html|main|article|body)\b", content, re.IGNORECASE):
        parser = _DocumentText()
        parser.feed(content)
        content = "".join(parser.parts)
    return [line.strip() for line in content.splitlines() if line.strip()]


def _changed_lines(before: str, after: str) -> tuple[list[str], list[str]]:
    old, new = _document_lines(before), _document_lines(after)
    added, removed = [], []
    for operation, i, j, k, m in SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if operation != "equal":
            removed.extend(old[i:j])
            added.extend(new[k:m])
    return added, removed
