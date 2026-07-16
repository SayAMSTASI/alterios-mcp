from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .gitea_workboard import GiteaConfig, sync_board_by_labels


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gitea_sync_board_by_labels",
        description="Sync Gitea project-board cards to columns based on issue stage:* labels.",
    )
    parser.add_argument("--dotenv", default=".env", help="Path to the private .env file.")
    parser.add_argument("--project-id", default=None, help="Gitea project board id. Defaults to GITEA_DEFAULT_PROJECT.")
    parser.add_argument("--state", choices=["open", "closed", "all"], default="open", help="Issue state to scan.")
    parser.add_argument("--limit", type=int, default=100, help="Issue read limit, from 1 to 100.")
    parser.add_argument("--apply-mode", choices=["auto", "api", "web"], default="auto", help="Board write backend.")
    parser.add_argument("--stage-column-map-json", default=None, help="JSON object mapping stage:* labels to board columns.")
    parser.add_argument("--stage-column-map-file", default=None, help="JSON file mapping stage:* labels to board columns.")
    parser.add_argument("--apply", action="store_true", help="Apply planned moves. Requires GITEA_MCP_ALLOW_WRITE=1.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    result = sync_board_by_labels(
        config=GiteaConfig.from_env(args.dotenv),
        project_id=args.project_id,
        stage_column_map=_load_stage_map(args.stage_column_map_json, args.stage_column_map_file),
        state=args.state,
        limit=args.limit,
        apply_mode=args.apply_mode,
        dry_run=not args.apply,
        dotenv_path=args.dotenv,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))


def _load_stage_map(raw_json: str | None, file_path: str | None) -> dict[str, str] | None:
    if raw_json and file_path:
        raise ValueError("Pass only one of --stage-column-map-json or --stage-column-map-file.")
    if file_path:
        raw_json = Path(file_path).read_text(encoding="utf-8")
    if not raw_json:
        return None
    value: Any = json.loads(raw_json)
    if not isinstance(value, dict):
        raise ValueError("Stage column map must be a JSON object.")
    return {str(key): str(item) for key, item in value.items()}


if __name__ == "__main__":
    main()
