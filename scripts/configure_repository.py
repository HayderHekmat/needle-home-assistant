"""Set HACS metadata to the actual public GitHub repository before publishing."""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository", help="GitHub OWNER/REPO")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("Expected OWNER/REPO")
    owner, _ = args.repository.split("/")
    url = f"https://github.com/{args.repository}"
    path = ROOT / "custom_components/needle/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update(
        documentation=f"{url}#readme",
        issue_tracker=f"{url}/issues",
        codeowners=[f"@{owner}"],
    )
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"HACS repository metadata configured for {url}")


if __name__ == "__main__":
    main()
