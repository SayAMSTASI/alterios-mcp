from __future__ import annotations

import json

import pytest

from alterios_mcp import server
from alterios_mcp.form_surface import analyze_form_surface, main


def test_validate_form_contract_tool_is_strict_alias() -> None:
    form = {"name": "Records", "tabs": []}

    analyzed = server.alterios_analyze_form_surface(form=form)
    validated = server.alterios_validate_form_contract(form=form)

    assert analyzed["surface"]["validation_profile"] == "default"
    assert analyzed["surface"]["ok"] is True
    assert validated["surface"]["validation_profile"] == "contract"
    assert validated["surface"]["ok"] is False
    assert validated["surface"]["blocking_issues_by_code"] == {"missing_page_title": 1}


def test_form_surface_accepts_clean_view_row() -> None:
    form = {
        "_id": "form-1",
        "name": "Sample Module",
        "pageTitle": "Sample Module",
        "tabs": [
            {
                "title": "List",
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"flex": "1 1 auto", "width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {"fields": {"title": {"title": "Name"}}},
                                "valueActionContainers": [
                                    {"actions": [{"title": "Edit", "iconId": "edit"}]},
                                    {"actions": [{"title": "View", "iconId": "visibility"}]},
                                    {"actions": [{"title": "Delete", "iconId": "delete"}]},
                                ],
                            }
                        ]
                    }
                ],
            }
        ],
    }

    result = analyze_form_surface(form)

    assert result["ok"] is True
    assert result["inventory"]["cell_types"] == {"view_data_list": 1}
    assert "missing_view_source" not in result["issues_by_code"]
    assert "row_action_order" not in result["issues_by_code"]


def test_form_surface_flags_view_row_with_empty_slot_and_missing_source() -> None:
    form = {
        "name": "Broken",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {"type": "view_data_list", "styles": {}, "displaying": {"fields": {}}},
                            {},
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form)

    assert result["ok"] is False
    assert result["issues_by_code"]["empty_layout_slot"] == 1
    assert result["issues_by_code"]["missing_view_source"] == 1
    assert result["issues_by_code"]["data_cell_missing_full_width_style"] == 1


def test_form_surface_flags_row_action_order_and_missing_icon() -> None:
    form = {
        "name": "Actions",
        "pageTitle": "Actions",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1"},
                                "displaying": {"fields": {"title": {}}},
                                "valueActionContainers": [
                                    {"actions": [{"title": "Delete", "iconId": "delete"}]},
                                    {"actions": [{"title": "Edit"}]},
                                    {"actions": [{"title": "View", "iconId": "visibility"}]},
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form)

    assert result["ok"] is True
    assert result["issues_by_code"]["row_action_order"] == 1
    assert result["issues_by_code"]["row_action_missing_icon"] == 1


def test_form_surface_understands_russian_row_action_titles() -> None:
    form = {
        "name": "Russian actions",
        "pageTitle": "Russian actions",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1"},
                                "displaying": {"fields": {"title": {}}},
                                "valueActionContainers": [
                                    {"title": "\u0423\u0434\u0430\u043b\u0438\u0442\u044c", "iconId": "delete", "actions": [{"type": "data_managing"}]},
                                    {"title": "\u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c", "iconId": "edit", "actions": [{"type": "forms"}]},
                                    {"title": "\u041f\u0440\u043e\u0441\u043c\u043e\u0442\u0440", "iconId": "visibility", "actions": [{"type": "forms"}]},
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form)

    assert result["issues_by_code"]["row_action_order"] == 1
    order_issue = next(issue for issue in result["issues"] if issue["code"] == "row_action_order")
    assert order_issue["details"]["observed"] == ["delete", "edit", "view"]


def test_form_surface_accepts_icon_on_action_container() -> None:
    form = {
        "name": "Container icon",
        "pageTitle": "Container icon",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1"},
                                "displaying": {"fields": {"title": {}}},
                                "valueActionContainers": [
                                    {
                                        "title": "Edit",
                                        "iconId": "edit",
                                        "actions": [{"type": "forms", "name": "Edit form"}],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form)

    assert "missing_action_icon" not in result["issues_by_code"]
    assert result["inventory"]["action_icons"] == ["edit"]


def test_form_surface_accepts_nested_row_menu_with_default_view() -> None:
    form = {
        "name": "Questions",
        "pageTitle": "Questions",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {"fields": {"title": {}}},
                                "valueActionContainers": [
                                    {
                                        "type": "menu",
                                        "iconId": "more_vert",
                                        "tooltip": "Menu",
                                        "actions": [],
                                        "containers": [
                                            {
                                                "type": "action",
                                                "title": "Edit",
                                                "iconId": "edit",
                                                "actions": [{"type": "forms", "name": "Edit form"}],
                                            },
                                            {
                                                "type": "action",
                                                "title": "View",
                                                "iconId": "preview",
                                                "default": True,
                                                "actions": [{"type": "forms", "name": "View form"}],
                                            },
                                            {
                                                "type": "action",
                                                "title": "Delete",
                                                "iconId": "delete",
                                                "actions": [{"type": "delete_contents"}],
                                            },
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form)

    assert result["ok"] is True
    assert "row_menu_missing_containers" not in result["issues_by_code"]
    assert "row_menu_default_view_missing" not in result["issues_by_code"]
    assert "row_action_container_should_be_menu" not in result["issues_by_code"]
    assert result["inventory"]["action_icons"] == ["delete", "edit", "more_vert", "preview"]


def test_form_surface_flags_multiple_row_actions_inside_plain_action_container() -> None:
    form = {
        "name": "Questions",
        "pageTitle": "Questions",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1"},
                                "displaying": {"fields": {"title": {}}},
                                "valueActionContainers": [
                                    {
                                        "type": "action",
                                        "iconId": "more_vert",
                                        "actions": [
                                            {"type": "forms", "title": "Edit", "iconId": "edit"},
                                            {"type": "forms", "title": "View", "iconId": "preview"},
                                            {"type": "delete_contents", "title": "Delete", "iconId": "delete"},
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form)

    assert result["issues_by_code"]["row_action_container_should_be_menu"] == 1


def test_form_surface_collects_roles_styles_and_report_source() -> None:
    form = {
        "name": "Report",
        "pageTitle": "Report",
        "roles": ["admin"],
        "tabs": [
            {
                "title": "Report",
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "report",
                                "styles": {"width": "100%", "fontWeight": "600"},
                                "params": {"reportId": "report-1", "openId": True},
                            }
                        ]
                    }
                ],
            }
        ],
    }

    result = analyze_form_surface(form)

    assert result["ok"] is True
    assert result["inventory"]["style_keys"]["fontWeight"] == 1
    assert result["inventory"]["data_sources"][0]["reportId"] == "report-1"
    assert result["inventory"]["role_keys"][0]["key"] == "roles"


def test_form_surface_flags_visible_title_on_element_action() -> None:
    form = {
        "name": "Question",
        "pageTitle": "Question",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1"},
                                "displaying": {"fields": {"title": {}}},
                                "cellActionContainers": [
                                    {
                                        "title": "Files",
                                        "iconId": "attach_file_add",
                                        "actions": [{"type": "forms"}],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form)

    assert result["issues_by_code"]["element_action_title_must_be_tooltip"] == 1


def test_form_surface_allows_titles_inside_nested_cell_menu_items() -> None:
    form = {
        "name": "Question",
        "pageTitle": "Question",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1"},
                                "displaying": {"fields": {"title": {}}},
                                "cellActionContainers": [
                                    {
                                        "type": "menu",
                                        "title": "",
                                        "tooltip": "Print",
                                        "iconId": "arrow_drop_down",
                                        "actions": [],
                                        "containers": [
                                            {
                                                "type": "action",
                                                "title": "Question and parameters",
                                                "iconId": "print",
                                                "actions": [{"type": "forms"}],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form)

    assert "element_action_title_must_be_tooltip" not in result["issues_by_code"]


def test_form_surface_allows_master_detail_action_hub_labels() -> None:
    form = {
        "name": "Direction panel",
        "pageTitle": "Direction panel",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "help",
                                "styles": {"width": "100%"},
                                "params": {"helpId": "help-1"},
                                "displaying": {"fields": {}},
                                "cellActionContainers": [
                                    {
                                        "type": "menu",
                                        "title": "Отчеты",
                                        "tooltip": "Печатные формы",
                                        "iconId": "arrow_drop_down",
                                        "position": "top_center",
                                        "actions": [],
                                        "containers": [
                                            {
                                                "type": "action",
                                                "title": "План верификации",
                                                "iconId": "print",
                                                "actions": [
                                                    {
                                                        "_id": "report-form-1",
                                                        "name": "План верификации. Отчет",
                                                        "type": "forms",
                                                        "openInDialog": False,
                                                        "openInNewTab": True,
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form)

    assert "element_action_title_must_be_tooltip" not in result["issues_by_code"]
    assert "report_or_analytics_form_should_open_new_tab" not in result["issues_by_code"]


def test_form_surface_checks_table_cell_header_style() -> None:
    form = {
        "name": "Question",
        "pageTitle": "Question",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "header": {"title": "Parameters", "styles": {"textAlign": "left", "fontWeight": "400"}},
                                "params": {"viewId": "view-1"},
                                "displaying": {"fields": {"title": {}}},
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form)

    assert result["issues_by_code"]["table_cell_header_style"] == 1


def test_form_surface_flags_non_table_cell_header() -> None:
    form = {
        "name": "Question",
        "pageTitle": "Question",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "header": {"title": "Question", "styles": {"textAlign": "center", "fontWeight": "bold"}},
                                "params": {"viewId": "view-1"},
                                "displaying": {"fields": {"title": {}}},
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form)

    assert result["issues_by_code"]["non_table_cell_header"] == 1


def test_form_surface_reads_runtime_displaying_header_and_checks_padding() -> None:
    form = {
        "name": "Параметры",
        "pageTitle": "Параметры",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {
                                    "fields": {"name": {}},
                                    "header": {
                                        "title": "Параметры",
                                        "styles": {
                                            "textAlign": "center",
                                            "fontWeight": "bold",
                                            "paddingTop": "8px",
                                        },
                                    },
                                },
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"] == {"table_cell_header_top_padding": 1}


def test_form_surface_contract_blocks_layout_gaps_and_wide_element_action_strip() -> None:
    form = {
        "name": "Редактировать параметр",
        "pageTitle": "Параметр",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {"fields": {"name": {}}},
                                "cellActionContainers": [
                                    {"type": "action", "iconId": f"icon-{index}", "actions": [{"type": "forms"}]}
                                    for index in range(4)
                                ],
                            },
                            {},
                        ]
                    }
                ]
            }
        ],
        "formActionContainers": [
            {"title": "Закрыть", "iconId": "close", "actions": [{"type": "routing", "routingType": "redirect_back"}]},
            {"title": "Сохранить", "iconId": "save", "actions": [{"type": "submit"}]},
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"]["empty_layout_slot"] == 1
    assert result["blocking_issues_by_code"]["element_actions_must_use_menu"] == 1


def test_form_surface_contract_blocks_nonstandard_add_page_title() -> None:
    form = {
        "name": "Показатели. Добавить",
        "pageTitle": "Показатели. Добавить",
        "tabs": [{"rows": [{"cells": [{"type": "content", "styles": {"width": "100%"}, "params": {"contentTypeId": "type-1"}}]}]}],
        "formActionContainers": [
            {"title": "Закрыть", "iconId": "close", "actions": [{"type": "routing", "routingType": "redirect_back"}]},
            {"title": "Сохранить", "iconId": "save", "actions": [{"type": "submit"}]},
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"] == {"add_page_title_must_start_with_add": 1}


def test_form_surface_flags_persistent_footnote_on_non_date_field() -> None:
    form = {
        "name": "Question",
        "pageTitle": "Question",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1"},
                                "displaying": {
                                    "fields": {
                                        "question_text": {
                                            "title": "Question",
                                            "hidden": False,
                                            "bottomText": "Fill this field carefully.",
                                        }
                                    }
                                },
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form, field_type_map={"question_text": "text"})

    assert result["issues_by_code"]["field_footnote_requires_date"] == 1
    assert result["inventory"]["field_footnotes"] == [
        {
            "path": "tabs[0].rows[0].cells[0].displaying.fields.question_text.bottomText",
            "field": "question_text",
            "key": "bottomText",
            "field_type": "text",
        }
    ]


def test_form_surface_allows_persistent_footnote_on_date_field() -> None:
    form = {
        "name": "Dates",
        "pageTitle": "Dates",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1"},
                                "displaying": {
                                    "fields": {
                                        "due_date": {
                                            "title": "Due date",
                                            "hidden": False,
                                            "helperText": "Use the document date.",
                                        }
                                    }
                                },
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form, field_type_map={"due_date": "date"})

    assert "field_footnote_requires_date" not in result["issues_by_code"]
    assert result["inventory"]["field_footnotes"][0]["field_type"] == "date"


def test_form_surface_does_not_treat_tooltip_as_bottom_footnote() -> None:
    form = {
        "name": "Tooltip",
        "pageTitle": "Tooltip",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1"},
                                "displaying": {
                                    "fields": {
                                        "question_text": {
                                            "title": "Question",
                                            "hidden": False,
                                            "tooltip": "Short help is allowed.",
                                        }
                                    }
                                },
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form, field_type_map={"question_text": "text"})

    assert "field_footnote_requires_date" not in result["issues_by_code"]
    assert result["inventory"]["field_footnotes"] == []


def test_form_surface_flags_print_or_analytics_form_opened_in_dialog() -> None:
    form = {
        "name": "Direction panel",
        "pageTitle": "Direction panel",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {"fields": {"title": {"hidden": False}}},
                                "cellActionContainers": [
                                    {
                                        "type": "menu",
                                        "title": "Отчеты",
                                        "iconId": "arrow_drop_down",
                                        "actions": [],
                                        "containers": [
                                            {
                                                "type": "action",
                                                "title": "План верификации",
                                                "iconId": "print",
                                                "actions": [
                                                    {
                                                        "_id": "report-form-1",
                                                        "name": "План верификации. Отчет",
                                                        "type": "forms",
                                                        "openInDialog": True,
                                                        "openInNewTab": False,
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form)

    assert result["issues_by_code"]["report_or_analytics_form_should_open_new_tab"] == 1
    issue = next(issue for issue in result["issues"] if issue["code"] == "report_or_analytics_form_should_open_new_tab")
    assert issue["details"]["name"] == "План верификации. Отчет"


def test_form_surface_accepts_print_or_analytics_form_opened_in_new_tab() -> None:
    form = {
        "name": "Direction panel",
        "pageTitle": "Direction panel",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {"fields": {"title": {"hidden": False}}},
                                "cellActionContainers": [
                                    {
                                        "type": "menu",
                                        "title": "Отчеты",
                                        "iconId": "arrow_drop_down",
                                        "actions": [],
                                        "containers": [
                                            {
                                                "type": "action",
                                                "title": "Акт верификации",
                                                "iconId": "print",
                                                "actions": [
                                                    {
                                                        "_id": "report-form-2",
                                                        "name": "Акт верификации. Отчет",
                                                        "type": "forms",
                                                        "openInDialog": False,
                                                        "openInNewTab": True,
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form)

    assert "report_or_analytics_form_should_open_new_tab" not in result["issues_by_code"]


def test_form_surface_contract_profile_blocks_confirmed_warning_codes() -> None:
    form = {
        "name": "Contract violations",
        "pageTitle": "Contract violations",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "header": {"title": "Details"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {
                                    "fields": {
                                        "title": {
                                            "hidden": False,
                                            "bottomText": "Persistent helper text",
                                        }
                                    }
                                },
                                "editing": {},
                                "cellActionContainers": [
                                    {
                                        "title": "Files",
                                        "iconId": "attach_file",
                                        "actions": [{"type": "forms"}],
                                    }
                                ],
                            }
                        ]
                    },
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "header": {
                                    "title": "Rows",
                                    "styles": {"textAlign": "left", "fontWeight": "400"},
                                },
                                "params": {"viewId": "view-2", "openId": True},
                                "displaying": {"fields": {"title": {"hidden": False}}},
                            }
                        ]
                    },
                ]
            }
        ],
    }

    default_result = analyze_form_surface(form, field_type_map={"title": "text"})
    contract_result = analyze_form_surface(form, field_type_map={"title": "text"}, strict=True)

    assert default_result["ok"] is True
    assert default_result["validation_profile"] == "default"
    assert default_result["blocking_issue_count"] == 0
    assert contract_result["ok"] is False
    assert contract_result["validation_profile"] == "contract"
    assert contract_result["blocking_issue_count"] == 5
    assert contract_result["blocking_issues_by_code"] == {
        "element_action_title_must_be_tooltip": 1,
        "field_footnote_requires_date": 1,
        "non_table_cell_header": 1,
        "table_cell_header_style": 1,
        "table_cell_header_top_padding": 1,
    }


def test_form_surface_contract_profile_blocks_close_without_redirect_back() -> None:
    form = {
        "name": "Details",
        "pageTitle": "Details",
        "tabs": [],
        "formActionContainers": [
            {
                "title": "Закрыть",
                "iconId": "close",
                "actions": [{"type": "routing", "routingType": "redirect"}],
            }
        ],
    }

    default_result = analyze_form_surface(form)
    contract_result = analyze_form_surface(form, strict=True)

    assert default_result["ok"] is True
    assert default_result["issues_by_code"]["close_action_missing_redirect_back"] == 1
    assert contract_result["ok"] is False
    assert contract_result["blocking_issues_by_code"] == {"close_action_missing_redirect_back": 1}


def test_form_surface_accepts_close_with_redirect_back_in_contract_profile() -> None:
    form = {
        "name": "Details",
        "pageTitle": "Details",
        "tabs": [],
        "formActionContainers": [
            {
                "title": "Закрыть",
                "iconId": "close",
                "actions": [{"type": "routing", "routingType": "redirect_back"}],
            }
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["ok"] is True
    assert "close_action_missing_redirect_back" not in result["issues_by_code"]


def test_form_surface_contract_profile_blocks_editable_view_detail_surface() -> None:
    form = {
        "name": "Question",
        "pageTitle": "Question",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {"fields": {"title": {"hidden": False}}},
                                "editing": {"enabled": True},
                            }
                        ]
                    }
                ]
            }
        ],
        "formActionContainers": [
            {
                "title": "Закрыть",
                "iconId": "close",
                "actions": [{"type": "routing", "routingType": "redirect_back"}],
            }
        ],
    }

    default_result = analyze_form_surface(form)
    contract_result = analyze_form_surface(form, strict=True)

    assert default_result["ok"] is True
    assert default_result["issues_by_code"]["view_detail_view_data_must_be_readonly"] == 1
    issue = next(
        issue for issue in contract_result["issues"] if issue["code"] == "view_detail_view_data_must_be_readonly"
    )
    assert contract_result["ok"] is False
    assert issue["path"] == "tabs[0].rows[0].cells[0].editing.enabled"
    assert issue["details"] == {"editing_enabled": True, "surface": "view/detail"}


def test_form_surface_allows_editable_view_data_on_submit_enabled_edit_form() -> None:
    form = {
        "name": "Edit question",
        "pageTitle": "Edit question",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {"fields": {"title": {"hidden": False}}},
                                "editing": {"enabled": True},
                            }
                        ]
                    }
                ]
            }
        ],
        "formActionContainers": [
            {
                "title": "Close",
                "iconId": "close",
                "actions": [{"type": "routing", "routingType": "redirect_back"}],
            },
            {
                "title": "Save",
                "iconId": "save",
                "actions": [{"type": "data_managing", "dataManagingType": "submit_all"}],
            }
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["ok"] is True
    assert "view_detail_view_data_must_be_readonly" not in result["issues_by_code"]


def test_form_surface_contract_blocks_embedded_view_without_filter_or_context() -> None:
    form = {
        "name": "Records",
        "pageTitle": "Records",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1"},
                                "displaying": {"fields": {"title": {"hidden": False}}},
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"] == {"embedded_view_missing_filter_or_context": 1}


def test_form_surface_contract_accepts_field_filter_and_hidden_technical_ids() -> None:
    form = {
        "name": "Records",
        "pageTitle": "Records",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1"},
                                "displaying": {
                                    "fields": {
                                        "title": {
                                            "hidden": False,
                                            "filter": {"mode": "standard", "enabled": True},
                                        },
                                        "_id": {"hidden": True},
                                        "contentId": {"hidden": "true"},
                                    }
                                },
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["ok"] is True
    assert "embedded_view_missing_filter_or_context" not in result["issues_by_code"]
    assert "technical_list_field_must_be_hidden" not in result["issues_by_code"]


def test_form_surface_contract_blocks_visible_technical_list_fields() -> None:
    form = {
        "name": "Records",
        "pageTitle": "Records",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {
                                    "fields": {
                                        "title": {"hidden": False},
                                        "_id": {},
                                        "_id0": {"hidden": False},
                                        "contentId": {"hidden": False},
                                    }
                                },
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"] == {"technical_list_field_must_be_hidden": 3}


def test_form_surface_contract_blocks_direct_list_row_actions() -> None:
    form = {
        "name": "Records",
        "pageTitle": "Records",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {"fields": {"title": {"hidden": False}}},
                                "valueActionContainers": [
                                    {
                                        "type": "action",
                                        "title": "Edit",
                                        "iconId": "edit",
                                        "actions": [{"type": "forms"}],
                                    },
                                    {
                                        "type": "action",
                                        "title": "View",
                                        "iconId": "preview",
                                        "actions": [{"type": "forms"}],
                                    },
                                    {
                                        "type": "action",
                                        "title": "Delete",
                                        "iconId": "delete",
                                        "actions": [{"type": "delete_contents"}],
                                    },
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"] == {"list_row_actions_must_be_menu": 1}


def test_form_surface_contract_blocks_incomplete_list_row_menu() -> None:
    form = {
        "name": "Records",
        "pageTitle": "Records",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {"fields": {"title": {"hidden": False}}},
                                "valueActionContainers": [
                                    {
                                        "type": "menu",
                                        "iconId": "more_vert",
                                        "actions": [],
                                        "containers": [
                                            {
                                                "type": "action",
                                                "title": "View",
                                                "iconId": "preview",
                                                "default": True,
                                                "actions": [{"type": "forms"}],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"] == {"list_row_menu_actions_missing": 1}


def test_form_surface_contract_blocks_row_menu_without_default_view() -> None:
    form = {
        "name": "Records",
        "pageTitle": "Records",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {"fields": {"title": {"hidden": False}}},
                                "valueActionContainers": [
                                    {
                                        "type": "menu",
                                        "iconId": "more_vert",
                                        "actions": [],
                                        "containers": [
                                            {
                                                "type": "action",
                                                "title": "Edit",
                                                "iconId": "edit",
                                                "actions": [{"type": "forms"}],
                                            },
                                            {
                                                "type": "action",
                                                "title": "View",
                                                "iconId": "preview",
                                                "actions": [{"type": "forms"}],
                                            },
                                            {
                                                "type": "action",
                                                "title": "Delete",
                                                "iconId": "delete",
                                                "actions": [{"type": "delete_contents"}],
                                            },
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"] == {"row_menu_default_view_missing": 1}


def test_form_surface_contract_blocks_list_row_action_without_icon() -> None:
    form = {
        "name": "Records",
        "pageTitle": "Records",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {"fields": {"title": {"hidden": False}}},
                                "valueActionContainers": [
                                    {
                                        "type": "menu",
                                        "iconId": "more_vert",
                                        "actions": [],
                                        "containers": [
                                            {
                                                "type": "action",
                                                "title": "Edit",
                                                "actions": [{"type": "forms"}],
                                            },
                                            {
                                                "type": "action",
                                                "title": "View",
                                                "iconId": "preview",
                                                "default": True,
                                                "actions": [{"type": "forms"}],
                                            },
                                            {
                                                "type": "action",
                                                "title": "Delete",
                                                "iconId": "delete",
                                                "actions": [{"type": "delete_contents"}],
                                            },
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"] == {"list_row_action_icon_missing": 1}


def test_form_surface_contract_blocks_report_form_action_not_opened_in_new_tab() -> None:
    form = {
        "name": "Direction panel",
        "pageTitle": "Direction panel",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {"fields": {"title": {"hidden": False}}},
                                "cellActionContainers": [
                                    {
                                        "type": "menu",
                                        "title": "",
                                        "tooltip": "Reports",
                                        "iconId": "arrow_drop_down",
                                        "actions": [],
                                        "containers": [
                                            {
                                                "type": "action",
                                                "title": "Report",
                                                "iconId": "print",
                                                "actions": [
                                                    {
                                                        "name": "Printable report",
                                                        "type": "forms",
                                                        "openInDialog": True,
                                                        "openInNewTab": False,
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
        "formActionContainers": [
            {
                "title": "Close",
                "iconId": "close",
                "actions": [{"type": "routing", "routingType": "redirect_back"}],
            }
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"] == {"report_or_analytics_form_should_open_new_tab": 1}


def test_form_surface_contract_blocks_report_target_without_close() -> None:
    form = {
        "name": "Printable record",
        "pageTitle": "Printable record",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "report",
                                "styles": {"width": "100%"},
                                "params": {"reportId": "report-1", "openId": True},
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"] == {"report_or_analytics_target_missing_close": 1}


def test_form_surface_contract_blocks_missing_page_title() -> None:
    form = {"name": "Records", "tabs": []}

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"] == {"missing_page_title": 1}


def test_form_surface_contract_blocks_add_edit_page_action_order() -> None:
    form = {
        "name": "Редактировать запись",
        "pageTitle": "Редактировать запись",
        "tabs": [],
        "formActionContainers": [
            {
                "title": "Сохранить",
                "iconId": "save",
                "actions": [{"type": "data_managing", "dataManagingType": "submit_all"}],
            },
            {
                "title": "Закрыть",
                "iconId": "close",
                "actions": [{"type": "routing", "routingType": "redirect_back"}],
            },
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"] == {"add_edit_page_action_order": 1}


def test_form_surface_contract_blocks_view_detail_without_close() -> None:
    form = {
        "name": "Просмотр записи",
        "pageTitle": "Просмотр записи",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {
                                    "fields": {
                                        "title": {
                                            "hidden": False,
                                            "outputConfig": {"outputType": "default"},
                                        }
                                    }
                                },
                            }
                        ]
                    }
                ]
            }
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"] == {"view_detail_close_action_missing": 1}


def test_form_surface_contract_blocks_editable_field_config_on_view_detail() -> None:
    form = {
        "name": "Показатель. Просмотр",
        "pageTitle": "Показатель",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data",
                                "styles": {"width": "100%"},
                                "params": {"viewId": "view-1", "openId": True},
                                "displaying": {
                                    "fields": {
                                        "name": {
                                            "hidden": False,
                                            "inputConfig": {"inputType": "text"},
                                        }
                                    }
                                },
                            }
                        ]
                    }
                ]
            }
        ],
        "formActionContainers": [
            {
                "title": "Закрыть",
                "iconId": "close",
                "actions": [{"type": "routing", "routingType": "redirect_back"}],
            }
        ],
    }

    result = analyze_form_surface(form, strict=True)

    assert result["blocking_issues_by_code"] == {
        "view_detail_field_input_config_present": 1,
        "view_detail_field_output_config_missing": 1,
    }


@pytest.mark.parametrize("flag", ["--strict", "--contract"])
def test_form_surface_cli_contract_flags_return_nonzero_for_contract_violation(tmp_path, capsys, flag: str) -> None:
    form = {
        "name": "Details",
        "pageTitle": "Details",
        "tabs": [],
        "formActionContainers": [
            {
                "title": "Закрыть",
                "iconId": "close",
                "actions": [{"type": "routing", "routingType": "redirect"}],
            }
        ],
    }
    json_path = tmp_path / "form.json"
    json_path.write_text(json.dumps(form, ensure_ascii=False), encoding="utf-8")

    assert main([str(json_path)]) == 0
    default_output = json.loads(capsys.readouterr().out)
    assert default_output["validation_profile"] == "default"

    assert main([str(json_path), flag]) == 1
    contract_output = json.loads(capsys.readouterr().out)
    assert contract_output["validation_profile"] == "contract"
    assert contract_output["blocking_issues_by_code"] == {"close_action_missing_redirect_back": 1}
def test_strict_contract_blocks_invalid_manual_script_value_action() -> None:
    result = analyze_form_surface(
        {
            "_id": "form-1",
            "name": "Rows",
            "pageTitle": "Rows",
            "tabs": [
                {
                    "rows": [
                        {
                            "cells": [
                                {
                                    "type": "view_data_list",
                                    "params": {"viewId": "view-1"},
                                    "styles": {"width": "100%"},
                                    "displaying": {"fields": {"name": {}}},
                                    "valueActionContainers": [
                                        {
                                            "type": "menu",
                                            "iconId": "menu-icon",
                                            "containers": [
                                                {
                                                    "type": "action",
                                                    "title": "Run",
                                                    "iconId": "script-icon",
                                                    "actions": [
                                                        {
                                                            "_id": "not-a-uuid",
                                                            "name": "Script",
                                                            "type": "manual_script",
                                                            "argumentsConfig": {
                                                                "type": "context",
                                                                "args": {"contentId": {}},
                                                            },
                                                        }
                                                    ],
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ]
                        }
                    ]
                }
            ],
        },
        strict=True,
    )

    assert result["ok"] is False
    assert result["blocking_issues_by_code"]["manual_script_id_must_be_uuid"] == 1
    assert result["blocking_issues_by_code"]["manual_script_empty_argument_binding"] == 1
