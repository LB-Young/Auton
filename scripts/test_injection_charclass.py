#!/usr/bin/env python
"""Test injection patterns - using explicit newline in char class"""
import re

NL = "\n"

# The issue: r"[\n`]" has backslash, n, backtick - NOT newline in the class!
# Solution: build the char class explicitly
# r"[\" + NL + "`]" would give: [\ <newline> `] - but that's ALSO wrong!
# The correct way: use the actual newline char INSIDE the char class

# In Python: "[\n`]" = [ followed by newline followed by backtick followed by ]
# YES! That's what we want!

pattern_str = "[\n" + "`" + "]"  # NOT a raw string! This is: [\n`]
print(f"Char class: {pattern_str!r}")
print(f"  len={len(pattern_str)}, chars: {[c for c in pattern_str]}")

p = re.compile("`{3,}(?![\n" + "`])")
print(f"\nFull pattern: {p.pattern!r}")

# Test
tests = [
    "text\n```\ncontent",        # should match (``` not followed by \n)
    "```\nmalicious\n```",  # should match only closing ``` (followed by end)
    "text```text",          # should match
]

for t in tests:
    result = p.sub("[CODE]", t)
    print(f"\n  input:  {t!r}")
    print(f"  output: {result!r}")
