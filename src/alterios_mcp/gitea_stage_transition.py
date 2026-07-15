from __future__ import annotations

import argparse
import json

from .gitea_workboard import GiteaConfig, transition_issue_stage


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gitea_transition_issue_stage",
        description="Replace an issue stage:* label and optionally sync the Gitea project board.",
    )
    parser.add_argument("issue_number", type=int, help="Issue number, for example 1.")
    parser.add_argument("target_stage", help="Target stage label, for example stage:verify or verify.")
    parser.add_argument("--dotenv", default=".env", help="Path to the private .env file.")
    parser.add_argument("--comment", default=None, help="Optional issue comment to add after the transition.")
    parser.add_argument("--sync-board", action="store_true", help="Try to sync Projects board after label transition.")
    parser.add_argument("--project-id", default=None, help="Gitea project board id. Defaults to GITEA_DEFAULT_PROJECT.")
    parser.add_argument("--apply-mode", choices=["auto", "api", "web"], default="auto", help="Board sync backend.")
    parser.add_argument("--apply", action="store_true", help="Apply transition. Requires GITEA_MCP_ALLOW_WRITE=1.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    result = transition_issue_stage(
        config=GiteaConfig.from_env(args.dotenv),
        issue_number=args.issue_number,
        target_stage=args.target_stage,
        comment=args.comment,
        sync_board=args.sync_board,
        project_id=args.project_id,
        apply_mode=args.apply_mode,
        dry_run=not args.apply,
        dotenv_path=args.dotenv,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
