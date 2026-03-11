"""
Command Parser
==============
Parses raw Discord message strings into structured ParsedCommand objects.

Supports two input styles:
  1. Slash-style: /server add --name mylab --host 10.0.0.5 --user ubuntu
  2. Natural-language: "add server mylab at 10.0.0.5"  (handled by Agent NL layer)

This module handles the slash-style path.
"""

from __future__ import annotations
import re
import shlex
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedCommand:
    """Structured representation of a parsed slash command."""
    group: str                          # "server" | "env" | "project" | "job" | "status"
    action: str                         # "add" | "list" | "use" | "test" | ...
    args: list[str] = field(default_factory=list)       # positional args
    flags: dict[str, str] = field(default_factory=dict) # --key value pairs
    raw: str = ""

    def flag(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Get a flag value by name (supports --name and -n)."""
        return self.flags.get(name, self.flags.get(name.lstrip("-"), default))

    def first_arg(self, default: Optional[str] = None) -> Optional[str]:
        return self.args[0] if self.args else default

    def rest_after_first(self) -> str:
        """Return all args after the first joined as a string."""
        return " ".join(self.args[1:]) if len(self.args) > 1 else ""


class CommandParser:
    """
    Parses /command style input from Discord messages.

    Examples:
        /server add --name mylab --host 10.0.0.5 --user ubuntu --port 22
        /server list
        /server use mylab
        /env list
        /project set /data/pbmc/
        /job log omics_abc123
    """

    # Maps (group, action) aliases → canonical form
    _ALIASES: dict[tuple[str, str], tuple[str, str]] = {
        ("server", "register"): ("server", "add"),
        ("server", "new"):      ("server", "add"),
        ("server", "connect"):  ("server", "use"),
        ("server", "switch"):   ("server", "use"),
        ("server", "delete"):   ("server", "remove"),
        ("server", "rm"):       ("server", "remove"),
        ("server", "ls"):       ("server", "list"),
        ("env", "activate"):    ("env", "use"),
        ("env", "switch"):      ("env", "use"),
        ("project", "cd"):      ("project", "set"),
        ("project", "ls"):      ("project", "ls"),
        ("job", "status"):      ("job", "status"),
        ("job", "ps"):          ("job", "list"),
    }

    def parse(self, message: str) -> Optional[ParsedCommand]:
        """
        Parse a message string into a ParsedCommand.
        Returns None if the message is not a slash command.
        """
        msg = message.strip()
        if not msg.startswith("/"):
            return None

        try:
            tokens = shlex.split(msg[1:])   # strip leading /
        except ValueError:
            tokens = msg[1:].split()

        if not tokens:
            return None

        # Determine group and action
        group = tokens[0].lower()
        if len(tokens) < 2:
            # Single-word command like /status
            return ParsedCommand(
                group=group, action="", args=[], flags={}, raw=message
            )

        action = tokens[1].lower()
        rest = tokens[2:]

        # Resolve aliases
        canonical = self._ALIASES.get((group, action), (group, action))
        group, action = canonical

        # Parse remaining tokens into positional args and --flags
        args, flags = self._parse_rest(rest)

        return ParsedCommand(
            group=group, action=action,
            args=args, flags=flags, raw=message
        )

    def _parse_rest(self, tokens: list[str]) -> tuple[list[str], dict[str, str]]:
        """
        Split tokens into positional args and --flag value pairs.

        Examples:
            ["mylab"]               → (["mylab"], {})
            ["--name", "mylab"]     → ([], {"name": "mylab"})
            ["mylab", "--port", "2222"] → (["mylab"], {"port": "2222"})
            ["--key"]               → ([], {"key": "true"})   # boolean flag
        """
        args: list[str] = []
        flags: dict[str, str] = {}
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok.startswith("--"):
                key = tok[2:]
                if "=" in key:
                    k, v = key.split("=", 1)
                    flags[k] = v
                elif i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                    flags[key] = tokens[i + 1]
                    i += 1
                else:
                    flags[key] = "true"
            elif tok.startswith("-") and len(tok) == 2:
                # Short flag like -p 2222
                key = tok[1:]
                if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                    flags[key] = tokens[i + 1]
                    i += 1
                else:
                    flags[key] = "true"
            else:
                args.append(tok)
            i += 1
        return args, flags
