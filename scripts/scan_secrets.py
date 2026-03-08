#!/usr/bin/env python3
"""Lightweight secret scanner for tracked/staged files.

Usage:
  python3 scripts/scan_secrets.py
  python3 scripts/scan_secrets.py --staged
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from typing import Iterable

SKIP_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".svg",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".pdf",
    ".zip",
    ".mp4",
    ".webm",
    ".db",
    ".sqlite",
    ".sqlite3",
}

SKIP_PREFIXES = (
    "node_modules/",
    ".venv/",
    "dist/",
    "build/",
    "coverage/",
    "__pycache__/",
    "data/",
)

ALLOW_SUBSTRINGS = (
    "your_",
    "example",
    "placeholder",
    "changeme",
    "dummy",
    "sample",
    "test_",
)

PATTERNS: dict[str, re.Pattern[str]] = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_pat": re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|DSA|PGP) PRIVATE KEY-----"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
}

ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|client[_-]?secret)\s*[:=]\s*['\"][^'\"]{8,}['\"]"
)


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()


def tracked_files() -> list[str]:
    out = run(["git", "ls-files"])
    return [line for line in out.splitlines() if line.strip()]


def staged_files() -> list[str]:
    out = run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    return [line for line in out.splitlines() if line.strip()]


def should_skip(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in SKIP_PREFIXES):
        return True
    _, ext = os.path.splitext(path.lower())
    return ext in SKIP_EXTENSIONS


def file_lines(path: str, staged: bool) -> Iterable[str]:
    if staged:
        try:
            content = subprocess.check_output(["git", "show", f":{path}"], text=True, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            return []
        return content.splitlines()

    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().splitlines()
    except OSError:
        return []


def is_allowed(line: str) -> bool:
    lower = line.lower()
    return any(token in lower for token in ALLOW_SUBSTRINGS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true", help="Scan staged files only")
    args = parser.parse_args()

    files = staged_files() if args.staged else tracked_files()
    findings: list[tuple[str, int, str, str]] = []

    for path in files:
        if should_skip(path):
            continue
        for idx, line in enumerate(file_lines(path, staged=args.staged), start=1):
            if not line.strip() or is_allowed(line):
                continue

            for name, pat in PATTERNS.items():
                if pat.search(line):
                    findings.append((path, idx, name, line.strip()))
                    break
            else:
                if ASSIGNMENT.search(line):
                    findings.append((path, idx, "sensitive_assignment", line.strip()))

    if findings:
        print("[secret-scan] Potential secrets found:")
        for path, idx, name, snippet in findings[:200]:
            print(f"- {path}:{idx} [{name}] {snippet[:220]}")
        print("\nCommit blocked. Remove secrets or replace with env vars/placeholders.")
        return 1

    print("[secret-scan] OK: no obvious secrets detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
