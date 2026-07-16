from __future__ import annotations

from .._support import *

def gitea_workboard_config(dotenv_path: str | None = None) -> dict[str, Any]:
    """Return redacted private Gitea workboard configuration and missing values."""
    env_path = dotenv_path or ".env"
    config = GiteaConfig.from_env(env_path)
    return {
        "config": config.redacted(),
        "missing_for_base_call": config.missing_for_base_call(),
        "missing_for_repo_call": config.missing_for_repo_call(),
        "write_enabled": gitea_write_enabled(env_path),
        "write_gate": "GITEA_MCP_ALLOW_WRITE=1",
    }

def gitea_workboard_probe(dotenv_path: str | None = None, include_repo: bool = True) -> dict[str, Any]:
    """Probe the configured private Gitea API and repository without changing state."""
    env_path = dotenv_path or ".env"
    config = GiteaConfig.from_env(env_path)
    result: dict[str, Any] = {
        "config": config.redacted(),
        "missing_for_base_call": config.missing_for_base_call(),
        "missing_for_repo_call": config.missing_for_repo_call(),
        "write_enabled": gitea_write_enabled(env_path),
    }
    if config.missing_for_base_call():
        result["api_version"] = {"skipped": True, "reason": "missing GITEA_BASE_URL"}
        result["repository"] = {"skipped": True, "reason": "missing GITEA_BASE_URL"}
        return result

    client = GiteaClient(config)
    result["api_version"] = client.api_version().as_dict()
    if not include_repo:
        result["repository"] = {"skipped": True, "reason": "include_repo=false"}
    elif config.missing_for_repo_call():
        result["repository"] = {"skipped": True, "missing": config.missing_for_repo_call()}
    else:
        result["repository"] = client.repository().as_dict()
    return result

def local_workboard_config(base_dir: str | None = None, dotenv_path: str | None = None) -> dict[str, Any]:
    """Return the local private workboard target used when Gitea is unavailable."""
    config = LocalWorkboardConfig.from_env(dotenv_path=dotenv_path or ".env", base_dir=base_dir)
    return {
        "config": config.redacted(),
        "exists": config.base_dir.exists(),
        "required_execution_gates": ["dry_run=false"],
    }

def local_workboard_init(base_dir: str | None = None, dotenv_path: str | None = None) -> dict[str, Any]:
    """Create the local private workboard folder structure."""
    return ensure_local_workboard(base_dir=base_dir, dotenv_path=dotenv_path or ".env")

def local_workboard_create_item(
    title: str,
    body: str,
    status: str = "backlog",
    kind: str = "task",
    sprint: str | None = None,
    labels: list[str] | None = None,
    assignee: str | None = None,
    base_dir: str | None = None,
    dotenv_path: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Plan or create a local private work item when Gitea is unavailable."""
    return create_local_work_item(
        title=title,
        body=body,
        status=status,
        kind=kind,
        sprint=sprint,
        labels=labels or [],
        assignee=assignee,
        base_dir=base_dir,
        dotenv_path=dotenv_path or ".env",
        dry_run=dry_run,
    )

def local_workboard_list_items(
    status: str | None = None,
    sprint: str | None = None,
    base_dir: str | None = None,
    dotenv_path: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List local private work items from the fallback file workboard."""
    return list_local_work_items(
        status=status,
        sprint=sprint,
        base_dir=base_dir,
        dotenv_path=dotenv_path or ".env",
        limit=limit,
    )

def local_workboard_add_agent_report(
    item_id: str,
    role: str,
    scope: str,
    findings: str,
    artifacts: str = "",
    verification: str = "",
    risks: str = "",
    next_step: str = "",
    body: str | None = None,
    base_dir: str | None = None,
    dotenv_path: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Plan or append a structured agent report to a local private work item."""
    return add_local_agent_report(
        item_id=item_id,
        role=role,
        scope=scope,
        findings=findings,
        artifacts=artifacts,
        verification=verification,
        risks=risks,
        next_step=next_step,
        body=body,
        base_dir=base_dir,
        dotenv_path=dotenv_path or ".env",
        dry_run=dry_run,
    )

def gitea_list_work_items(
    state: str = "open",
    labels: list[str] | None = None,
    milestones: list[str] | None = None,
    query: str | None = None,
    limit: int = 20,
    dotenv_path: str | None = None,
) -> dict[str, Any]:
    """List private Gitea issue work items from the configured workboard repository."""
    if state not in {"open", "closed", "all"}:
        raise ValueError("state must be one of: open, closed, all.")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100.")
    config = GiteaConfig.from_env(dotenv_path or ".env")
    response = GiteaClient(config).list_issues(
        state=state,
        labels=labels or [],
        milestones=milestones or [],
        query=query,
        limit=limit,
    )
    return {
        "target": config.target(),
        "state": state,
        "labels": labels or [],
        "milestones": milestones or [],
        "query": query,
        "response": response.as_dict(),
    }

def gitea_sync_standard_labels(
    template_path: str = "templates/gitea/labels.yaml",
    dry_run: bool = True,
    dotenv_path: str | None = None,
) -> dict[str, Any]:
    """Plan or create the standard private-workboard labels in Gitea."""
    env_path = dotenv_path or ".env"
    config = GiteaConfig.from_env(env_path)
    labels = load_standard_labels(template_path)
    planned_payload = {"template_path": template_path, "label_count": len(labels), "labels": labels}
    if dry_run:
        return planned_gitea_result(
            operation="gitea_sync_standard_labels",
            config=config,
            dry_run=True,
            payload=planned_payload,
            response={"will_check_existing_labels_on_apply": True},
            dotenv_path=env_path,
        )

    assert_gitea_write_allowed(config, dry_run=False, dotenv_path=env_path)
    client = GiteaClient(config)
    existing_response = client.list_labels()
    existing_labels = existing_response.body if isinstance(existing_response.body, list) else []
    existing_names = {str(label.get("name")) for label in existing_labels if isinstance(label, dict)}
    created = []
    skipped = []
    for label in labels:
        if label["name"] in existing_names:
            skipped.append(label["name"])
            continue
        created_response = client.create_label(label).as_dict()
        created.append({"name": label["name"], "response": created_response})
    return planned_gitea_result(
        operation="gitea_sync_standard_labels",
        config=config,
        dry_run=False,
        payload=planned_payload,
        response={
            "created_count": len(created),
            "skipped_count": len(skipped),
            "created": created,
            "skipped": skipped,
        },
        dotenv_path=env_path,
    )

def gitea_create_work_item(
    title: str,
    body: str,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    milestone_id: int | None = None,
    milestone_name: str | None = None,
    due_date: str | None = None,
    ref: str | None = None,
    dry_run: bool = True,
    dotenv_path: str | None = None,
) -> dict[str, Any]:
    """Plan or create a private Gitea issue work item for real project work."""
    env_path = dotenv_path or ".env"
    config = GiteaConfig.from_env(env_path)
    effective_milestone = milestone_id if milestone_id is not None else (milestone_name or config.default_milestone)
    planned_payload = {
        "title": title.strip(),
        "body": body,
        "label_names": labels or [],
        "assignees": assignees or [],
        "milestone": effective_milestone,
        "due_date": due_date,
        "ref": ref,
    }
    if dry_run:
        return planned_gitea_result(
            operation="gitea_create_work_item",
            config=config,
            dry_run=True,
            payload=planned_payload,
            response={"will_resolve_label_and_milestone_ids_on_apply": True},
            dotenv_path=env_path,
        )

    assert_gitea_write_allowed(config, dry_run=False, dotenv_path=env_path)
    client = GiteaClient(config)
    label_ids = client.resolve_label_ids(labels or [])
    resolved_milestone_id = client.resolve_milestone_id(effective_milestone)
    issue_payload = build_issue_payload(
        title=title,
        body=body,
        label_ids=label_ids,
        assignees=assignees or [],
        milestone_id=resolved_milestone_id,
        due_date=due_date,
        ref=ref,
    )
    response = client.create_issue(issue_payload).as_dict()
    return planned_gitea_result(
        operation="gitea_create_work_item",
        config=config,
        dry_run=False,
        payload={**planned_payload, "resolved_label_ids": label_ids, "resolved_milestone_id": resolved_milestone_id},
        response=response,
        dotenv_path=env_path,
    )

def gitea_create_sprint(
    title: str | None = None,
    description: str = "",
    due_on: str | None = None,
    state: str = "open",
    dry_run: bool = True,
    dotenv_path: str | None = None,
) -> dict[str, Any]:
    """Plan or create a Gitea milestone used as a sprint for the private workboard."""
    if state not in {"open", "closed"}:
        raise ValueError("state must be one of: open, closed.")
    env_path = dotenv_path or ".env"
    config = GiteaConfig.from_env(env_path)
    sprint_title = (title or config.default_milestone).strip()
    if not sprint_title:
        raise ValueError("title must not be empty and GITEA_DEFAULT_MILESTONE is not configured.")
    payload = {
        "title": sprint_title,
        "description": description,
        "due_on": due_on,
        "state": state,
    }
    if dry_run:
        return planned_gitea_result(
            operation="gitea_create_sprint",
            config=config,
            dry_run=True,
            payload=payload,
            response={"will_create_only_if_missing": True},
            dotenv_path=env_path,
        )

    assert_gitea_write_allowed(config, dry_run=False, dotenv_path=env_path)
    response = GiteaClient(config).ensure_milestone(
        title=sprint_title,
        description=description,
        due_on=due_on,
        state=state,
    )
    return planned_gitea_result(
        operation="gitea_create_sprint",
        config=config,
        dry_run=False,
        payload=payload,
        response=response,
        dotenv_path=env_path,
    )

def gitea_list_sprint_tasks(
    milestone: str | None = None,
    state: str = "open",
    labels: list[str] | None = None,
    limit: int = 50,
    dotenv_path: str | None = None,
) -> dict[str, Any]:
    """List Gitea issue work items for one sprint/milestone."""
    if state not in {"open", "closed", "all"}:
        raise ValueError("state must be one of: open, closed, all.")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100.")
    config = GiteaConfig.from_env(dotenv_path or ".env")
    sprint = (milestone or config.default_milestone).strip()
    if not sprint:
        raise ValueError("milestone must not be empty and GITEA_DEFAULT_MILESTONE is not configured.")
    response = GiteaClient(config).list_issues(
        state=state,
        labels=labels or [],
        milestones=[sprint],
        limit=limit,
    )
    return {
        "target": config.target(),
        "milestone": sprint,
        "state": state,
        "labels": labels or [],
        "response": response.as_dict(),
    }

def gitea_add_agent_report(
    issue_number: int,
    role: str,
    scope: str,
    findings: str,
    inputs: str = "",
    artifacts: str = "",
    verification: str = "",
    risks: str = "",
    next_step: str = "",
    body: str | None = None,
    dry_run: bool = True,
    dotenv_path: str | None = None,
) -> dict[str, Any]:
    """Plan or add a structured agent report comment to a private Gitea work item."""
    if issue_number < 1:
        raise ValueError("issue_number must be positive.")
    env_path = dotenv_path or ".env"
    config = GiteaConfig.from_env(env_path)
    comment_body = body or agent_report_body(
        role=role,
        scope=scope,
        inputs=inputs,
        findings=findings,
        artifacts=artifacts,
        verification=verification,
        risks=risks,
        next_step=next_step,
    )
    payload = {"issue_number": issue_number, "body": comment_body}
    if dry_run:
        return planned_gitea_result(
            operation="gitea_add_agent_report",
            config=config,
            dry_run=True,
            payload=payload,
            dotenv_path=env_path,
        )

    assert_gitea_write_allowed(config, dry_run=False, dotenv_path=env_path)
    response = GiteaClient(config).create_issue_comment(issue_number, comment_body).as_dict()
    return planned_gitea_result(
        operation="gitea_add_agent_report",
        config=config,
        dry_run=False,
        payload=payload,
        response=response,
        dotenv_path=env_path,
    )

def gitea_sync_board_by_labels(
    project_id: str | None = None,
    stage_column_map: dict[str, str] | None = None,
    state: str = "open",
    limit: int = 100,
    apply_mode: str = "auto",
    dry_run: bool = True,
    dotenv_path: str | None = None,
) -> dict[str, Any]:
    """Move Gitea project-board cards into columns based on issue stage:* labels."""
    env_path = dotenv_path or ".env"
    return sync_board_by_labels(
        config=GiteaConfig.from_env(env_path),
        project_id=project_id,
        stage_column_map=stage_column_map,
        state=state,
        limit=limit,
        apply_mode=apply_mode,
        dry_run=dry_run,
        dotenv_path=env_path,
    )

def gitea_transition_issue_stage(
    issue_number: int,
    target_stage: str,
    comment: str | None = None,
    sync_board: bool = False,
    project_id: str | None = None,
    apply_mode: str = "auto",
    dry_run: bool = True,
    dotenv_path: str | None = None,
) -> dict[str, Any]:
    """Replace an issue stage:* label and optionally sync the Projects board."""
    env_path = dotenv_path or ".env"
    return transition_issue_stage(
        config=GiteaConfig.from_env(env_path),
        issue_number=issue_number,
        target_stage=target_stage,
        comment=comment,
        sync_board=sync_board,
        project_id=project_id,
        apply_mode=apply_mode,
        dry_run=dry_run,
        dotenv_path=env_path,
    )

__all__ = ['gitea_workboard_config', 'gitea_workboard_probe', 'local_workboard_config', 'local_workboard_init', 'local_workboard_create_item', 'local_workboard_list_items', 'local_workboard_add_agent_report', 'gitea_list_work_items', 'gitea_sync_standard_labels', 'gitea_create_work_item', 'gitea_create_sprint', 'gitea_list_sprint_tasks', 'gitea_add_agent_report', 'gitea_sync_board_by_labels', 'gitea_transition_issue_stage']
