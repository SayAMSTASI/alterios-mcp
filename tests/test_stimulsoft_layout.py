from __future__ import annotations

from alterios_mcp.stimulsoft_layout import analyze_stimulsoft_layout


def test_layout_analyzer_accepts_clean_dashboard_template() -> None:
    template = {
        "Pages": {
            "0": {
                "Ident": "StiDashboard",
                "Width": 1280,
                "Height": 720,
                "Components": {
                    "0": {
                        "Ident": "StiTextElement",
                        "Name": "Title",
                        "ClientRectangle": "24,24,900,56",
                    },
                    "1": {
                        "Ident": "StiTextElement",
                        "Name": "Metric",
                        "ClientRectangle": "24,104,320,80",
                    },
                },
            }
        }
    }

    result = analyze_stimulsoft_layout(template)

    assert result["ok"] is True
    assert result["component_count"] == 2
    assert result["issue_count"] == 0


def test_layout_analyzer_detects_visible_overlap() -> None:
    template = {
        "Pages": {
            "0": {
                "Width": 200,
                "Height": 100,
                "Components": {
                    "0": {"Ident": "StiText", "Name": "Left", "ClientRectangle": "10,10,80,20"},
                    "1": {"Ident": "StiText", "Name": "Right", "ClientRectangle": "50,10,80,20"},
                },
            }
        }
    }

    result = analyze_stimulsoft_layout({"template": template})

    assert result["issue_count"] == 1
    assert result["issues"][0]["code"] == "component_overlap"
    assert result["issues"][0]["details"]["components"] == ["Left", "Right"]


def test_layout_analyzer_detects_dynamic_height_without_shift_mode() -> None:
    template = {
        "Pages": {
            "0": {
                "Width": 200,
                "Height": 200,
                "Components": {
                    "Band": {
                        "Ident": "StiDataBand",
                        "Name": "Rows",
                        "ClientRectangle": "0,0,200,100",
                        "Components": {
                            "0": {
                                "Ident": "StiText",
                                "Name": "Comment",
                                "ClientRectangle": "10,10,150,20",
                                "CanGrow": True,
                            },
                            "1": {
                                "Ident": "StiText",
                                "Name": "StaticCol",
                                "ClientRectangle": "165,10,25,20",
                            },
                            "2": {
                                "Ident": "StiText",
                                "Name": "Below",
                                "ClientRectangle": "10,35,150,20",
                            },
                        },
                    }
                },
            }
        }
    }

    result = analyze_stimulsoft_layout(template)

    assert result["issues_by_code"]["dynamic_height_without_shift"] == 1
    assert result["issues_by_code"]["mixed_row_dynamic_height"] == 1


def test_layout_analyzer_flags_page_overflow() -> None:
    template = {
        "Pages": {
            "0": {
                "Width": 100,
                "Height": 100,
                "Components": {
                    "0": {"Ident": "StiText", "Name": "TooWide", "ClientRectangle": "80,10,40,20"}
                },
            }
        }
    }

    result = analyze_stimulsoft_layout(template)

    assert result["issues_by_code"]["page_width_overflow"] == 1


def test_layout_analyzer_treats_print_bands_as_vertical_flow() -> None:
    template = {
        "Pages": {
            "0": {
                "Ident": "StiPage",
                "Width": 19,
                "Height": 27.7,
                "Components": {
                    "0": {"Ident": "StiReportTitleBand", "Name": "Title", "ClientRectangle": "0,0,19,1.4"},
                    "1": {"Ident": "StiPageHeaderBand", "Name": "Header", "ClientRectangle": "0,0,19,0.8"},
                    "2": {"Ident": "StiDataBand", "Name": "Data", "ClientRectangle": "0,0,19,0.8"},
                    "3": {"Ident": "StiPageFooterBand", "Name": "Footer", "ClientRectangle": "0,0,19,0.6"},
                },
            }
        }
    }

    result = analyze_stimulsoft_layout(template)

    assert result["ok"] is True
    assert "component_overlap" not in result["issues_by_code"]
