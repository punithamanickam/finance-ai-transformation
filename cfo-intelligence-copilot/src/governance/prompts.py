"""Versioned prompt registry. Prompts live in /prompts/*.md with a front-matter version line and are
hashed so the audit log proves exactly which prompt text produced an answer."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from src import settings


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:16]

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}#{self.sha256}"


def load_prompt(name: str) -> Prompt:
    raw = (settings.PROMPTS_DIR / f"{name}.md").read_text()
    m = re.match(r"^---\s*\nversion:\s*(\S+)\s*\n---\s*\n", raw)
    version = m.group(1) if m else "unversioned"
    body = raw[m.end():] if m else raw
    return Prompt(name, version, body.strip())
