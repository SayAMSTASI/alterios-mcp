from __future__ import annotations

from .._support import *

def alterios_file_metadata(
    file_ids: list[str],
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios file metadata for one or more file IDs."""
    return _client(profile, project_id).file_metadata(file_ids).as_dict()

def alterios_list_project_icons(
    folder_hash: str | None = None,
    icons_folder_name: str | None = None,
    recurse: bool = False,
    verify_registry: bool = True,
    save_artifact: bool = True,
    max_files: int = 5000,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Inventory project-local MCP icon registry and optionally elFinder file-manager icons."""
    config = AlteriosConfig.from_env(profile=profile).with_project_id(project_id)
    missing = config.missing_for_project_call()
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")
    target_profile = config.profile or "<default>"
    target_project_id = config.project_id
    registry = _read_project_icon_registry(profile=target_profile, project_id=target_project_id)
    registry_icons = registry.get("icons") or {}
    client = AlteriosClient(config)

    registry_rows = []
    for semantic in sorted(registry_icons):
        entry = registry_icons[semantic]
        file_id = str((entry or {}).get("file_id") or "") if isinstance(entry, dict) else ""
        registry_rows.append(
            {
                "semantic": semantic,
                "google_name": entry.get("google_name") if isinstance(entry, dict) else None,
                "file_id": file_id or None,
                "filename": entry.get("filename") if isinstance(entry, dict) else None,
                "source": entry.get("source") if isinstance(entry, dict) else None,
                "exists": _project_icon_file_exists(client, file_id) if verify_registry and file_id else None,
            }
        )

    filesystem: dict[str, Any] | None = None
    if folder_hash or icons_folder_name:
        resolved_hash, folder_info = _resolve_elfinder_icon_folder(
            client,
            folder_hash=folder_hash or PROJECT_ICON_FOLDER_HASH,
            icons_folder_name=icons_folder_name,
        )
        icons, directories = _collect_elfinder_icon_items(
            client,
            folder_hash=resolved_hash,
            recurse=recurse,
            max_files=max_files,
        )
        catalog = _group_icon_catalog(icons)
        filesystem = {
            "folder": folder_info,
            "recurse": recurse,
            "icon_count": len(icons),
            "directory_count": len(directories),
            "icons": icons,
            "catalog": catalog,
        }
        if save_artifact:
            out_dir = artifact_root() / "project-icons" / _safe_artifact_component(target_profile) / _safe_artifact_component(target_project_id)
            out_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = out_dir / "filesystem-icons.json"
            manifest_path.write_text(json.dumps(filesystem, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            filesystem["artifact"] = _relative_artifact_path(manifest_path)

    coverage = []
    filesystem_icons = (filesystem or {}).get("icons") or []
    for semantic, google_name in sorted(PROJECT_ICON_DEFAULTS.items()):
        registry_entry = registry_icons.get(semantic)
        candidates = _filesystem_icon_candidates(filesystem_icons, semantic=semantic, google_name=google_name) if filesystem else []
        coverage.append(
            {
                "semantic": semantic,
                "google_name": google_name,
                "registry_file_id": registry_entry.get("file_id") if isinstance(registry_entry, dict) else None,
                "filesystem_candidate_count": len(candidates),
                "filesystem_sample": candidates[:3],
            }
        )

    return {
        "target": {"profile": target_profile, "project_id": target_project_id},
        "registry": {
            "path": _relative_artifact_path(_project_icon_registry_path(profile=target_profile, project_id=target_project_id)),
            **_icon_registry_summary(registry),
            "icons": registry_rows,
        },
        "filesystem": filesystem,
        "standard_coverage": coverage,
    }

def alterios_resolve_project_icon(
    semantic: str,
    google_name: str | None = None,
    folder_hash: str | None = None,
    icons_folder_name: str | None = None,
    recurse: bool = False,
    save_registry_match: bool = True,
    allow_upload: bool = True,
    dry_run: bool = True,
    plan_id: str | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Resolve one semantic icon to a project-local iconId using registry, file-manager scan, or guarded upload."""
    spec = _normalize_project_icon_specs(
        [{"semantic": semantic, "google_name": google_name or ""}],
        include_defaults=False,
    )[0]
    semantic = spec["semantic"]
    google_name = spec["google_name"]
    config = AlteriosConfig.from_env(profile=profile).with_project_id(project_id)
    missing = config.missing_for_project_call()
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")
    target_profile = config.profile or "<default>"
    target_project_id = config.project_id
    client = AlteriosClient(config)
    registry = _read_project_icon_registry(profile=target_profile, project_id=target_project_id)
    registry_icons = registry.setdefault("icons", {})
    entry = registry_icons.get(semantic)
    file_id = str((entry or {}).get("file_id") or "") if isinstance(entry, dict) else ""
    if (
        isinstance(entry, dict)
        and file_id
        and entry.get("source") in {"project_file_manager", "repo_icon_library"}
        and _project_icon_file_exists(client, file_id)
    ):
        return {
            "target": {"profile": target_profile, "project_id": target_project_id},
            "semantic": semantic,
            "google_name": google_name,
            "resolved": True,
            "source": "registry",
            "registry_source": entry.get("source"),
            "icon_id": file_id,
            "registry": {"path": _relative_artifact_path(_project_icon_registry_path(profile=target_profile, project_id=target_project_id))},
        }
    if _registry_icon_current(entry, google_name=google_name, size=16, color="#4B77D1", style="materialsymbolsoutlined") and _project_icon_file_exists(client, file_id):
        return {
            "target": {"profile": target_profile, "project_id": target_project_id},
            "semantic": semantic,
            "google_name": google_name,
            "resolved": True,
            "source": "registry",
            "icon_id": file_id,
            "registry": {"path": _relative_artifact_path(_project_icon_registry_path(profile=target_profile, project_id=target_project_id))},
        }

    filesystem_candidates: list[dict[str, Any]] = []
    folder_info = None
    if folder_hash or icons_folder_name:
        resolved_hash, folder_info = _resolve_elfinder_icon_folder(
            client,
            folder_hash=folder_hash or PROJECT_ICON_FOLDER_HASH,
            icons_folder_name=icons_folder_name,
        )
        filesystem_icons, _directories = _collect_elfinder_icon_items(
            client,
            folder_hash=resolved_hash,
            recurse=recurse,
            max_files=5000,
        )
        filesystem_candidates = _filesystem_icon_candidates(filesystem_icons, semantic=semantic, google_name=google_name)
        if filesystem_candidates:
            selected = filesystem_candidates[0]
            if save_registry_match:
                registry_icons[semantic] = {
                    "semantic": semantic,
                    "google_name": google_name,
                    "file_id": selected["file_id"],
                    "filename": selected["name"],
                    "size": 16,
                    "color": "#4B77D1",
                    "style": "materialsymbolsoutlined",
                    "source": "project_file_manager",
                    "matched_by": "semantic_guess",
                    "hash": selected.get("hash"),
                    "url": selected.get("url"),
                }
                _write_project_icon_registry(profile=target_profile, project_id=target_project_id, registry=registry)
            return {
                "target": {"profile": target_profile, "project_id": target_project_id},
                "semantic": semantic,
                "google_name": google_name,
                "resolved": True,
                "source": "filesystem",
                "icon_id": selected["file_id"],
                "selected": selected,
                "candidate_count": len(filesystem_candidates),
                "folder": folder_info,
                "registry_updated": save_registry_match,
            }

    if not allow_upload:
        return {
            "target": {"profile": target_profile, "project_id": target_project_id},
            "semantic": semantic,
            "google_name": google_name,
            "resolved": False,
            "source": "not_found",
            "filesystem_candidates": filesystem_candidates,
            "folder": folder_info,
        }

    upload_plan = alterios_ensure_project_icons(
        icon_specs=[{"semantic": semantic, "google_name": google_name}],
        include_defaults=False,
        dry_run=dry_run,
        plan_id=plan_id,
        profile=profile,
        project_id=project_id,
    )
    return {
        "target": {"profile": target_profile, "project_id": target_project_id},
        "semantic": semantic,
        "google_name": google_name,
        "resolved": not dry_run,
        "source": "upload_plan" if dry_run else "uploaded",
        "upload": upload_plan,
        "filesystem_candidates": filesystem_candidates,
        "folder": folder_info,
    }

def alterios_export_project_icons(
    folder_hash: str | None = None,
    icons_folder_name: str | None = None,
    recurse: bool = False,
    download_files: bool = True,
    max_files: int = 5000,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Export icons from an Alterios elFinder folder to local artifacts with a generated usage guide."""
    config = AlteriosConfig.from_env(profile=profile).with_project_id(project_id)
    missing = config.missing_for_project_call()
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")
    target_profile = config.profile or "<default>"
    target_project_id = config.project_id
    client = AlteriosClient(config)
    resolved_hash, folder_info = _resolve_elfinder_icon_folder(
        client,
        folder_hash=folder_hash or PROJECT_ICON_FOLDER_HASH,
        icons_folder_name=icons_folder_name,
    )
    icons, directories = _collect_elfinder_icon_items(
        client,
        folder_hash=resolved_hash,
        recurse=recurse,
        max_files=max_files,
    )
    catalog = _group_icon_catalog(icons)
    out_dir = _icon_export_directory(profile=target_profile, project_id=target_project_id, folder_info=folder_info)
    files_dir = out_dir / "files"
    out_dir.mkdir(parents=True, exist_ok=True)
    if download_files:
        files_dir.mkdir(parents=True, exist_ok=True)
        for icon in icons:
            file_id = str(icon["file_id"])
            filename = _safe_download_filename(file_id, str(icon.get("name") or "icon"))
            data, content_type, download_source = _download_elfinder_icon_file(client, icon)
            file_path = files_dir / filename
            file_path.write_bytes(data)
            icon["download"] = {
                "path": _relative_artifact_path(file_path),
                "content_type": content_type,
                "source": download_source,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
    manifest = {
        "target": {"profile": target_profile, "project_id": target_project_id},
        "folder": folder_info,
        "recurse": recurse,
        "download_files": download_files,
        "icon_count": len(icons),
        "directory_count": len(directories),
        "icons": icons,
        "catalog": catalog,
    }
    manifest_path = out_dir / "exported-icons.json"
    guide_path = out_dir / "icon-usage-guide.md"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_icon_usage_guide(guide_path, profile=target_profile, project_id=target_project_id, catalog=catalog, icons=icons)
    return {
        "target": {"profile": target_profile, "project_id": target_project_id},
        "folder": folder_info,
        "icon_count": len(icons),
        "unique_semantics": len(catalog),
        "downloaded": download_files,
        "artifacts": {
            "manifest": _relative_artifact_path(manifest_path),
            "usage_guide": _relative_artifact_path(guide_path),
            "files_dir": _relative_artifact_path(files_dir) if download_files else None,
        },
        "catalog_sample": catalog[:20],
    }

def _icon_export_directory(*, profile: str, project_id: str, folder_info: dict[str, Any]) -> Path:
    folder_slug = _safe_artifact_component(str(folder_info.get("folder_name") or folder_info.get("folder_hash") or "folder"))
    return (
        artifact_root()
        / "project-icons"
        / _safe_artifact_component(profile)
        / _safe_artifact_component(project_id)
        / "exports"
        / folder_slug
    )

def alterios_ensure_project_icons(
    icon_specs: list[dict[str, str]] | None = None,
    include_defaults: bool = True,
    force_upload: bool = False,
    dry_run: bool = True,
    plan_id: str | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or upload Google Fonts Icons into one Alterios project and return UUID iconId values."""
    size = 16
    color = "#4B77D1"
    style = "materialsymbolsoutlined"
    if not ICON_COLOR_RE.fullmatch(color):
        raise ValueError("Icon color must be a #RRGGBB value.")

    normalized_specs = _normalize_project_icon_specs(icon_specs, include_defaults=include_defaults)
    operation = _project_icon_operation(
        icon_specs=normalized_specs,
        size=size,
        color=color,
        style=style,
        force_upload=force_upload,
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    target = audit.as_dict()["target"]
    target_profile = str(target["profile"])
    target_project_id = str(target["project_id"])
    registry = _read_project_icon_registry(profile=target_profile, project_id=target_project_id)
    registry_path = _project_icon_registry_path(profile=target_profile, project_id=target_project_id)

    planned_icons = []
    for spec in normalized_specs:
        semantic = spec["semantic"]
        google_name = spec["google_name"]
        entry = (registry.get("icons") or {}).get(semantic)
        reusable = (not force_upload) and _registry_icon_current(
            entry,
            google_name=google_name,
            size=size,
            color=color,
            style=style,
        )
        filename = _project_icon_filename(semantic=semantic, google_name=google_name, size=size, color=color)
        planned_icons.append(
            {
                "semantic": semantic,
                "google_name": google_name,
                "filename": filename,
                "planned_action": "reuse_registry" if reusable else "upload_google_icon",
                "file_id": entry.get("file_id") if reusable and isinstance(entry, dict) else None,
            }
        )

    response_payload: dict[str, Any] = {
        "principle": {
            "source": "Google Fonts Icons",
            "upload_first": True,
            "icon_id_rule": "Use only UUID values returned by /api/file/upload/icon in forms, groups, and actions.",
            "size": size,
            "color": color,
            "style": style,
        },
        "registry": {
            "path": _relative_artifact_path(registry_path),
            **_icon_registry_summary(registry),
        },
        "icons": planned_icons,
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)

    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    if not plan_id:
        raise ValueError("plan_id is required when dry_run=false for alterios_ensure_project_icons.")
    assert_plan_matches_audit(plan_id=plan_id, audit=audit.as_dict())

    client = _client(profile, project_id)
    registry_icons = registry.setdefault("icons", {})
    ensured_icons = []
    for spec in normalized_specs:
        semantic = spec["semantic"]
        google_name = spec["google_name"]
        entry = registry_icons.get(semantic)
        file_id = str((entry or {}).get("file_id") or "") if isinstance(entry, dict) else ""
        if (
            not force_upload
            and _registry_icon_current(entry, google_name=google_name, size=size, color=color, style=style)
            and _project_icon_file_exists(client, file_id)
        ):
            ensured_icons.append(
                {
                    "semantic": semantic,
                    "google_name": google_name,
                    "file_id": file_id,
                    "action": "reused_registry",
                }
            )
            continue

        svg = _download_google_icon_svg(google_name=google_name, style=style, size=size, color=color)
        filename = _project_icon_filename(semantic=semantic, google_name=google_name, size=size, color=color)
        uploaded = client.upload_icon(svg, filename=filename).as_dict()
        uploaded_id = _extract_response_id(uploaded)
        if not uploaded_id:
            raise ValueError(f"Icon upload for {semantic!r} returned no file id.")
        metadata = client.file_metadata([uploaded_id]).as_dict()
        registry_icons[semantic] = {
            "semantic": semantic,
            "google_name": google_name,
            "file_id": uploaded_id,
            "filename": filename,
            "size": size,
            "color": color,
            "style": style,
            "source": _google_icon_url(google_name=google_name, style=style),
            "sha256": hashlib.sha256(svg).hexdigest(),
            "render_size": 20,
            "file_contract_verified": True,
        }
        ensured_icons.append(
            {
                "semantic": semantic,
                "google_name": google_name,
                "file_id": uploaded_id,
                "filename": filename,
                "action": "uploaded",
                "metadata": metadata,
            }
        )

    registry_path_result = _write_project_icon_registry(
        profile=target_profile,
        project_id=target_project_id,
        registry=registry,
    )
    response_payload.update(
        {
            "registry": {
                "path": registry_path_result,
                **_icon_registry_summary(registry),
            },
            "icons": ensured_icons,
            "icon_ids": {item["semantic"]: item["file_id"] for item in ensured_icons},
        }
    )
    return controlled_write_result(audit=audit, response=response_payload, plan_id=plan_id)

def alterios_ensure_project_icon_library(
    semantics: list[str] | None = None,
    library_dir: str | None = None,
    folder_hash: str | None = None,
    icons_folder_name: str | None = None,
    recurse: bool = False,
    force_upload: bool = False,
    dry_run: bool = True,
    plan_id: str | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Ensure repo-stored project icons exist in one Alterios project and return project-local iconId values."""
    base_dir, library_icons = _read_project_icon_library(library_dir=library_dir, semantics=semantics)
    selected_semantics = [str(icon["semantic"]) for icon in library_icons]
    scan_hash = folder_hash or PROJECT_PUBLIC_FOLDER_HASH
    operation = _project_icon_library_operation(
        library_dir=str(base_dir),
        semantics=selected_semantics,
        folder_hash=scan_hash,
        icons_folder_name=icons_folder_name,
        recurse=recurse,
        force_upload=force_upload,
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    target = audit.as_dict()["target"]
    target_profile = str(target["profile"])
    target_project_id = str(target["project_id"])
    config = AlteriosConfig.from_env(profile=profile).with_project_id(project_id)
    missing = config.missing_for_project_call()
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")
    client = AlteriosClient(config)

    registry = _read_project_icon_registry(profile=target_profile, project_id=target_project_id)
    registry_icons = registry.setdefault("icons", {})
    resolved_hash, folder_info = _resolve_elfinder_icon_folder(
        client,
        folder_hash=scan_hash,
        icons_folder_name=icons_folder_name,
    )
    filesystem_icons, directories = _collect_elfinder_icon_items(
        client,
        folder_hash=resolved_hash,
        recurse=recurse,
        max_files=5000,
    )

    planned_icons: list[dict[str, Any]] = []
    for library_icon in library_icons:
        semantic = str(library_icon["semantic"])
        entry = registry_icons.get(semantic)
        file_id = str((entry or {}).get("file_id") or "") if isinstance(entry, dict) else ""
        reusable_registry = (
            not force_upload
            and isinstance(entry, dict)
            and entry.get("source") == "repo_icon_library"
            and entry.get("sha256") == library_icon["sha256"]
            and file_id
            and _project_icon_file_exists(client, file_id)
        )
        candidates = _filesystem_icon_candidates(filesystem_icons, semantic=semantic, google_name=semantic)
        selected_candidate = candidates[0] if candidates else None
        if reusable_registry:
            planned_action = "reuse_registry"
            planned_file_id = file_id
        elif selected_candidate and not force_upload:
            planned_action = "register_project_file"
            planned_file_id = selected_candidate.get("file_id")
        else:
            planned_action = "upload_library_icon"
            planned_file_id = None
        planned_icons.append(
            {
                "semantic": semantic,
                "filename": library_icon["filename"],
                "mime": library_icon["mime"],
                "sha256": library_icon["sha256"],
                "planned_action": planned_action,
                "file_id": planned_file_id,
                "filesystem_candidate_count": len(candidates),
                "filesystem_sample": candidates[:3],
            }
        )

    registry_path = _project_icon_registry_path(profile=target_profile, project_id=target_project_id)
    response_payload: dict[str, Any] = {
        "principle": {
            "source": "repo project icon library",
            "analyze_project_before_upload": True,
            "upload_only_missing": not force_upload,
            "icon_id_rule": "Use only target-project-local file UUID values as iconId; never copy iconId values between projects.",
        },
        "library": {
            "path": str(base_dir),
            "icon_count": len(library_icons),
            "semantics": selected_semantics,
        },
        "inventory": {
            "folder": folder_info,
            "recurse": recurse,
            "filesystem_icon_count": len(filesystem_icons),
            "filesystem_directory_count": len(directories),
            "registry": {
                "path": _relative_artifact_path(registry_path),
                **_icon_registry_summary(registry),
            },
        },
        "icons": planned_icons,
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)

    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    if not plan_id:
        raise ValueError("plan_id is required when dry_run=false for alterios_ensure_project_icon_library.")
    assert_plan_matches_audit(plan_id=plan_id, audit=audit.as_dict())

    ensured_icons: list[dict[str, Any]] = []
    for planned in planned_icons:
        semantic = str(planned["semantic"])
        library_icon = next(icon for icon in library_icons if icon["semantic"] == semantic)
        if planned["planned_action"] == "reuse_registry" and planned.get("file_id"):
            ensured_icons.append(
                {
                    "semantic": semantic,
                    "file_id": planned["file_id"],
                    "filename": library_icon["filename"],
                    "action": "reused_registry",
                }
            )
            continue
        if planned["planned_action"] == "register_project_file" and planned.get("file_id"):
            selected = (planned.get("filesystem_sample") or [{}])[0]
            registry_icons[semantic] = {
                "semantic": semantic,
                "file_id": planned["file_id"],
                "filename": selected.get("name") or library_icon["filename"],
                "mime": selected.get("mime") or library_icon["mime"],
                "source": "project_file_manager",
                "matched_by": "semantic_guess",
                "hash": selected.get("hash"),
                "library_sha256": library_icon["sha256"],
                "source_size": library_icon["source_size"],
                "render_size": library_icon["render_size"],
                "color": library_icon["color"],
                "file_contract_verified": library_icon["file_contract_verified"],
            }
            ensured_icons.append(
                {
                    "semantic": semantic,
                    "file_id": planned["file_id"],
                    "filename": selected.get("name") or library_icon["filename"],
                    "action": "registered_project_file",
                }
            )
            continue

        data = Path(library_icon["path"]).read_bytes()
        uploaded = client.upload_icon(
            data,
            filename=str(library_icon["filename"]),
            mime_type=str(library_icon["mime"]),
        ).as_dict()
        uploaded_id = _extract_response_id(uploaded)
        if not uploaded_id:
            raise ValueError(f"Icon upload for {semantic!r} returned no file id.")
        metadata = client.file_metadata([uploaded_id]).as_dict()
        registry_icons[semantic] = {
            "semantic": semantic,
            "file_id": uploaded_id,
            "filename": library_icon["filename"],
            "mime": library_icon["mime"],
            "source": "repo_icon_library",
            "library_path": str(Path(library_icon["path"]).relative_to(base_dir)),
            "sha256": library_icon["sha256"],
            "source_size": library_icon["source_size"],
            "render_size": library_icon["render_size"],
            "color": library_icon["color"],
            "file_contract_verified": library_icon["file_contract_verified"],
        }
        ensured_icons.append(
            {
                "semantic": semantic,
                "file_id": uploaded_id,
                "filename": library_icon["filename"],
                "action": "uploaded_library_icon",
                "metadata": metadata,
            }
        )

    registry_path_result = _write_project_icon_registry(
        profile=target_profile,
        project_id=target_project_id,
        registry=registry,
    )
    response_payload.update(
        {
            "inventory": {
                **response_payload["inventory"],
                "registry": {
                    "path": registry_path_result,
                    **_icon_registry_summary(registry),
                },
            },
            "icons": ensured_icons,
            "icon_ids": {item["semantic"]: item["file_id"] for item in ensured_icons},
        }
    )
    return controlled_write_result(audit=audit, response=response_payload, plan_id=plan_id)

__all__ = ['alterios_file_metadata', 'alterios_list_project_icons', 'alterios_resolve_project_icon', 'alterios_export_project_icons', 'alterios_ensure_project_icons', 'alterios_ensure_project_icon_library']
