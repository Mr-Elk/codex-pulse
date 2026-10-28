"""Check repository-local Markdown links without network access or extra packages.

Supports inline/image/reference links, fenced and inline code, HTML comments,
URL-encoded paths, link titles, Markdown headings and explicit HTML anchors.
Only Git-tracked files can satisfy local targets; generated local files cannot.
"""
from __future__ import annotations

import argparse
from html import unescape
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = {".md", ".markdown"}


def blank(text):
    return re.sub(r"[^\r\n]", " ", text)


def without_blocks(text):
    text = re.sub(r"<!--[\s\S]*?-->", lambda match: blank(match[0]), text)
    result, fence = [], None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            result.append(blank(line))
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                if not line[marker.end():].strip():
                    fence = None
        elif marker:
            fence = marker[1]
            result.append(blank(line))
        else:
            result.append(line)
    return "".join(result)


def without_inline_code(text):
    result, previous, position = [], 0, 0
    while position < len(text):
        if text[position] != "`":
            position += 1
            continue
        end = position
        while end < len(text) and text[end] == "`":
            end += 1
        run = text[position:end]
        closing = re.search(r"(?<!`)" + re.escape(run) + r"(?!`)", text[end:])
        if closing:
            stop = end + closing.end()
            result.extend((text[previous:position], blank(text[position:stop])))
            previous = position = stop
        else:
            position = end
    return "".join(result) + text[previous:]


def destination(text, start, *, inline):
    """Read a destination while preserving nested or escaped path parentheses."""
    position = start
    while position < len(text) and text[position].isspace():
        position += 1
    value, depth = [], 0
    angled = position < len(text) and text[position] == "<"
    if angled:
        position += 1
    while position < len(text):
        char = text[position]
        if char == "\\" and position + 1 < len(text):
            value.append(text[position + 1])
            position += 2
            continue
        if angled:
            if char == ">":
                position += 1
                break
        elif depth == 0 and (char.isspace() or char == ")"):
            break
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        value.append(char)
        position += 1
    else:
        if angled or depth:
            return None
    if not inline:
        return unescape("".join(value)), position
    while position < len(text) and text[position].isspace():
        position += 1
    if position < len(text) and text[position] in "\"'(":
        closing = ")" if text[position] == "(" else text[position]
        position += 1
        while position < len(text):
            if text[position] == "\\":
                position += 2
            elif text[position] == closing:
                position += 1
                break
            else:
                position += 1
        while position < len(text) and text[position].isspace():
            position += 1
    if position < len(text) and text[position] == ")":
        return unescape("".join(value)), position + 1
    return None


def reference_key(text):
    return " ".join(text.split()).casefold()


def links(text):
    text = without_inline_code(without_blocks(text))
    references = {}
    definition = re.compile(r"^ {0,3}\[([^\]\n]+)\]:[ \t]*(.*)$", re.MULTILINE)
    for match in definition.finditer(text):
        parsed = destination(match[2], 0, inline=False)
        if parsed:
            references.setdefault(reference_key(match[1]), parsed[0])
    text = definition.sub(lambda match: blank(match[0]), text)
    for opening, char in enumerate(text):
        if char != "[" or (opening and text[opening - 1] == "\\"):
            continue
        closing, depth = opening + 1, 1
        while closing < len(text) and depth:
            if text[closing] == "\\":
                closing += 2
                continue
            if text[closing] == "[":
                depth += 1
            elif text[closing] == "]":
                depth -= 1
            closing += 1
        if depth:
            continue
        label = text[opening + 1:closing - 1]
        target = None
        if closing < len(text) and text[closing] == "(":
            parsed = destination(text, closing + 1, inline=True)
            if parsed:
                target = parsed[0]
        elif closing < len(text) and text[closing] == "[":
            end = text.find("]", closing + 1)
            if end != -1:
                key = text[closing + 1:end] or label
                target = references.get(reference_key(key))
        else:
            target = references.get(reference_key(label))
        if target is not None:
            yield target, text.count("\n", 0, opening) + 1


class ExplicitAnchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.anchors = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if value and (key == "id" or (tag == "a" and key == "name")):
                self.anchors.add(value)


def anchors(text):
    text = without_blocks(text)
    html = ExplicitAnchors()
    html.feed(text)
    found, used = set(html.anchors), set()
    previous = ""
    for line in text.splitlines():
        heading = re.match(r"^ {0,3}#{1,6}[ \t]+(.+?)(?:[ \t]+#+[ \t]*)?$", line)
        title = heading[1] if heading else None
        if previous.strip() and re.fullmatch(r" {0,3}(?:=+|-+)[ \t]*", line):
            title = previous.strip()
        previous = line
        if title is None:
            continue
        title = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", title)
        title = re.sub(r"<[^>]+>", "", title)
        title = re.sub(r"`+|\*+|~~|(?<!\w)_+|_+(?!\w)", "", title)
        slug = re.sub(r"[^\w\- ]", "", unescape(title).lower().strip()).replace(" ", "-")
        value, suffix = slug, 0
        while value in used:
            suffix += 1
            value = f"{slug}-{suffix}"
        used.add(value)
        found.add(value)
    return found


def check(root):
    root = Path(root).resolve()
    listed = subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=root)
    tracked = set(listed.decode("utf-8").rstrip("\0").split("\0")) - {""}
    directories = {str(p) for name in tracked for p in PurePosixPath(name).parents}
    problems, cache = [], {}

    def read(name):
        if name not in cache:
            path = root / name
            if not path.resolve().is_relative_to(root):
                raise ValueError("target resolves outside repository")
            cache[name] = path.read_text(encoding="utf-8")
        return cache[name]

    for source in sorted(tracked):
        if Path(source).suffix.lower() not in MARKDOWN:
            continue
        try:
            body = read(source)
        except (OSError, UnicodeError, ValueError) as error:
            problems.append(f"{source}: cannot read tracked Markdown ({type(error).__name__})")
            continue
        for target, line in links(body):
            reason = None
            try:
                parts = urlsplit(target)
                if parts.scheme or parts.netloc:
                    continue
                decoded = unquote(parts.path, errors="strict")
                name = (posixpath.normpath(decoded.lstrip("/")) if decoded.startswith("/")
                        else posixpath.normpath(posixpath.join(posixpath.dirname(source), decoded))
                        if decoded else source)
                if name == ".." or name.startswith("../"):
                    reason = "target escapes repository"
                elif name not in tracked and name not in directories:
                    reason = "target is not tracked by Git (including filename case)"
                elif not (root / name).exists():
                    reason = "tracked target is missing from checkout"
                elif not (root / name).resolve().is_relative_to(root):
                    reason = "target resolves outside repository"
                elif parts.fragment and Path(name).suffix.lower() in MARKDOWN:
                    fragment = unquote(parts.fragment, errors="strict")
                    if fragment not in anchors(read(name)):
                        reason = f"Markdown anchor does not exist: {fragment!r}"
            except (OSError, UnicodeError, ValueError) as error:
                reason = f"cannot resolve target ({type(error).__name__})"
            if reason:
                problems.append(f"{source}:{line}: {target!r}: {reason}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        problems = check(args.root)
    except (OSError, UnicodeError, subprocess.CalledProcessError) as error:
        print(f"Cannot inspect repository: {type(error).__name__}: {error}")
        return 2
    if problems:
        print("\n".join(problems))
        return 1
    print("All tracked Markdown local links and Markdown anchors resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
