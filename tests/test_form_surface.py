from __future__ import annotations

from alterios_mcp.form_surface import analyze_form_surface


def test_form_surface_accepts_clean_view_row() -> None:
    form = {
        "_id": "form-1",
        "name": "MCP Practice",
        "pageTitle": "MCP Practice",
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
    assert result["issues_by_code"]["missing_action_icon"] == 1


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
