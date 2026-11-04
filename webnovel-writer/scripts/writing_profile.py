#!/usr/bin/env python3
"""Read and validate a project's authoritative writing configuration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_modules.writing_profile import load_rule_bundles, load_writing_profile
from runtime_compat import enable_windows_utf8_stdio


def main() -> None:
    parser = argparse.ArgumentParser(description="读取市场、正文语言和固定版本规则包")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--format", choices=["json"], default="json")
    parser.add_argument("--bundles", action="store_true")
    args = parser.parse_args()
    try:
        profile = load_writing_profile(Path(args.project_root))
        payload = {"profile": profile.to_snapshot(), "reference": profile.reference()}
        if args.bundles:
            payload["bundles"] = load_rule_bundles(profile)
    except ValueError as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    enable_windows_utf8_stdio()
    main()
