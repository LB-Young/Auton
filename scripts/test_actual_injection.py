#!/usr/bin/env python
"""Test the ACTUAL escape_injection from injection.py"""
import sys
sys.path.insert(0, '.')

from auton.security.injection import escape_injection, is_injection_suspect, _INJECTION_PATTERNS

print("=== Patterns used ===")
for i, (pat, repl) in enumerate(_INJECTION_PATTERNS):
    print(f"  {i}: {pat.pattern!r} -> {repl!r}")

print()
print("=== escape_injection ===")
tests = [
    ("some text\n```\nmalicious\n", "unclosed block mid-text"),
    ("```\nmalicious", "block at start, no close"),
    ("text\n```\ncontent", "block in middle, no close"),
    ("```\nmalicious\n```", "properly closed block"),
    ("```\n", "just opening block"),
    ("normal\n# system: hacked\n", "comment injection"),
    ("---\n", "standalone HR"),
    ("normal\n---\nmore", "inline HR"),
    ("normal text", "clean text"),
    ("text\n```\n", "unclosed at end of string"),
]

for text, desc in tests:
    result = escape_injection(text)
    suspect = is_injection_suspect(text)
    print(f"  {desc}:")
    print(f"    input:  {text!r}")
    print(f"    output: {result!r}")
    print(f"    suspect: {suspect}")
