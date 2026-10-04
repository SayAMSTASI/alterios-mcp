# Каталог инструментов MCP

Версия пакета: `0.3.0`.

Сгенерировано командой `python -m alterios_mcp.capabilities`. Не редактировать вручную.

Этот каталог подтверждает регистрацию инструментов и доступность в профилях; он не подтверждает проверку на живом контуре.

| Профиль | Инструментов |
|---|---:|
| full | 118 |
| live | 91 |
| discovery | 65 |
| admin | 116 |

| Инструмент | Класс | full | live | discovery | admin |
|---|---|---|---|---|---|
| `alterios_add_comment` | typed_write | да | да | — | да |
| `alterios_analyze_form_surface` | read_only_discovery | да | да | да | да |
| `alterios_audit_log` | read_only_discovery | да | да | да | да |
| `alterios_bulk_update_selected_content_fields` | typed_write | да | да | — | да |
| `alterios_call_readonly_service` | read_only_discovery | да | — | да | да |
| `alterios_call_write_service` | raw_write_escape_hatch | да | — | — | — |
| `alterios_clone_shared_content_type` | typed_write | да | да | — | да |
| `alterios_complete_task` | typed_write | да | да | — | да |
| `alterios_config` | runtime_guard | да | да | да | да |
| `alterios_create_content` | typed_write | да | да | — | да |
| `alterios_create_material_module` | scenario | да | да | — | да |
| `alterios_create_process_flow` | scenario | да | да | — | да |
| `alterios_create_report_tab` | scenario | да | да | — | да |
| `alterios_delete_role` | admin_security_write | да | — | — | да |
| `alterios_delete_user` | admin_security_write | да | — | — | да |
| `alterios_delete_user_group` | admin_security_write | да | — | — | да |
| `alterios_diagnose_report_viewer` | read_only_discovery | да | да | да | да |
| `alterios_diagnose_view` | read_only_discovery | да | да | да | да |
| `alterios_discover_readonly` | read_only_discovery | да | — | да | да |
| `alterios_download_files` | read_only_discovery | да | да | да | да |
| `alterios_ensure_project_icon_library` | typed_write | да | да | — | да |
| `alterios_ensure_project_icons` | typed_write | да | да | — | да |
| `alterios_execute_manual_script` | typed_write | да | да | — | да |
| `alterios_export_dataset` | read_only_discovery | да | да | да | да |
| `alterios_export_project_icons` | typed_write | да | — | — | да |
| `alterios_fast_live_bulk_delete` | dangerous_workflow | да | — | — | да |
| `alterios_fast_live_bulk_manual_script` | scenario | да | да | — | да |
| `alterios_fast_live_bulk_process` | scenario | да | да | — | да |
| `alterios_fast_live_write` | scenario | да | да | — | да |
| `alterios_file_metadata` | read_only_discovery | да | да | да | да |
| `alterios_file_upload_to_field` | typed_write | да | да | — | да |
| `alterios_find_usages` | read_only_discovery | да | да | да | да |
| `alterios_get_form` | read_only_discovery | да | да | да | да |
| `alterios_get_role` | read_only_discovery | да | — | да | да |
| `alterios_get_user` | read_only_discovery | да | — | да | да |
| `alterios_get_user_group` | read_only_discovery | да | — | да | да |
| `alterios_get_view` | read_only_discovery | да | да | да | да |
| `alterios_get_write_plan` | read_only_discovery | да | да | да | да |
| `alterios_list_comments` | read_only_discovery | да | да | да | да |
| `alterios_list_content_types` | read_only_discovery | да | да | да | да |
| `alterios_list_fields` | read_only_discovery | да | да | да | да |
| `alterios_list_files` | read_only_discovery | да | да | да | да |
| `alterios_list_groups` | read_only_discovery | да | да | да | да |
| `alterios_list_notifications` | read_only_discovery | да | да | да | да |
| `alterios_list_objects` | read_only_discovery | да | да | да | да |
| `alterios_list_process_tasks` | read_only_discovery | да | да | да | да |
| `alterios_list_profiles` | runtime_guard | да | да | да | да |
| `alterios_list_project_icons` | read_only_discovery | да | да | да | да |
| `alterios_list_projects` | read_only_discovery | да | да | да | да |
| `alterios_list_roles` | read_only_discovery | да | — | да | да |
| `alterios_list_user_groups` | read_only_discovery | да | — | да | да |
| `alterios_list_users` | read_only_discovery | да | — | да | да |
| `alterios_list_write_plans` | read_only_discovery | да | да | да | да |
| `alterios_live_task_preflight` | runtime_guard | да | да | да | да |
| `alterios_patch_form_actions` | typed_write | да | да | — | да |
| `alterios_patch_form_cell_listeners` | typed_write | да | да | — | да |
| `alterios_patch_form_tabs` | typed_write | да | да | — | да |
| `alterios_patch_report_template` | typed_write | да | да | — | да |
| `alterios_plan_content_type_publish` | typed_write | да | да | — | да |
| `alterios_profile_smoke_matrix` | runtime_guard | да | да | да | да |
| `alterios_project_health` | runtime_guard | да | да | да | да |
| `alterios_read_all_objects` | read_only_discovery | да | да | да | да |
| `alterios_relation_graph` | read_only_discovery | да | да | да | да |
| `alterios_replay_smoke` | runtime_guard | да | да | да | да |
| `alterios_report_full` | read_only_discovery | да | да | да | да |
| `alterios_resolve_project_icon` | read_only_discovery | да | да | да | да |
| `alterios_rest_get` | read_only_discovery | да | — | да | да |
| `alterios_rest_write` | raw_write_escape_hatch | да | — | — | — |
| `alterios_runtime_info` | runtime_guard | да | да | да | да |
| `alterios_service_catalog` | read_only_discovery | да | — | да | да |
| `alterios_start_process` | typed_write | да | да | — | да |
| `alterios_tool_profile` | introspection | да | да | да | да |
| `alterios_update_content_fields` | typed_write | да | да | — | да |
| `alterios_upsert_bpmn_diagram` | typed_write | да | да | — | да |
| `alterios_upsert_content_type` | typed_write | да | да | — | да |
| `alterios_upsert_field` | typed_write | да | да | — | да |
| `alterios_upsert_form` | typed_write | да | да | — | да |
| `alterios_upsert_form_manual_script_action` | typed_write | да | да | — | да |
| `alterios_upsert_group` | typed_write | да | да | — | да |
| `alterios_upsert_help` | typed_write | да | да | — | да |
| `alterios_upsert_report` | typed_write | да | да | — | да |
| `alterios_upsert_role` | admin_security_write | да | — | — | да |
| `alterios_upsert_script` | typed_write | да | да | — | да |
| `alterios_upsert_user` | admin_security_write | да | — | — | да |
| `alterios_upsert_user_group` | admin_security_write | да | — | — | да |
| `alterios_upsert_view` | typed_write | да | да | — | да |
| `alterios_upsert_view_entity` | typed_write | да | да | — | да |
| `alterios_upsert_view_field` | typed_write | да | да | — | да |
| `alterios_ux_contract` | runtime_guard | да | да | да | да |
| `alterios_validate_form_contract` | read_only_discovery | да | да | да | да |
| `alterios_validate_module_contract` | read_only_discovery | да | да | да | да |
| `alterios_validate_printable_render` | read_only_discovery | да | да | да | да |
| `alterios_validate_process_result` | read_only_discovery | да | да | да | да |
| `alterios_validate_report_project_base` | read_only_discovery | да | да | да | да |
| `alterios_validate_script` | read_only_discovery | да | да | да | да |
| `alterios_validate_stimulsoft_layout` | read_only_discovery | да | да | да | да |
| `alterios_verify_delivery_evidence` | runtime_guard | да | да | да | да |
| `alterios_view_data` | read_only_discovery | да | да | да | да |
| `alterios_view_data_simplified` | read_only_discovery | да | да | да | да |
| `alterios_view_entities` | read_only_discovery | да | да | да | да |
| `alterios_view_fields_populated` | read_only_discovery | да | да | да | да |
| `alterios_write_journal` | read_only_discovery | да | да | да | да |
| `alterios_write_safety_preflight` | runtime_guard | да | да | да | да |
| `gitea_add_agent_report` | work_coordination | да | да | — | да |
| `gitea_create_sprint` | work_coordination | да | — | — | да |
| `gitea_create_work_item` | work_coordination | да | да | — | да |
| `gitea_list_sprint_tasks` | work_coordination | да | да | да | да |
| `gitea_list_work_items` | work_coordination | да | да | да | да |
| `gitea_sync_board_by_labels` | work_coordination | да | да | — | да |
| `gitea_sync_standard_labels` | work_coordination | да | — | — | да |
| `gitea_transition_issue_stage` | work_coordination | да | да | — | да |
| `gitea_workboard_config` | work_coordination | да | да | да | да |
| `gitea_workboard_probe` | work_coordination | да | да | да | да |
| `local_workboard_add_agent_report` | work_coordination | да | — | — | да |
| `local_workboard_config` | work_coordination | да | — | да | да |
| `local_workboard_create_item` | work_coordination | да | — | — | да |
| `local_workboard_init` | work_coordination | да | — | — | да |
| `local_workboard_list_items` | work_coordination | да | — | да | да |
