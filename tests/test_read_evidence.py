import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from alterios_mcp import read_evidence as e
from alterios_mcp.response_output import present
from alterios_mcp.performance import json_bytes
from alterios_mcp.read_freshness import check_freshness
from alterios_mcp.write_control import ControlledWriteError
from alterios_mcp.scenarios import read_workflows as tools, views_forms

TARGET = {"profile": "test", "project_id": "project-one"}


@pytest.fixture(autouse=True)
def private_results(tmp_path, monkeypatch):
    monkeypatch.setenv("ALTERIOS_MCP_ARTIFACTS_DIR", str(tmp_path))


def saved(payload, **options):
    return present(payload, target=TARGET, source={"mode": "live", "observed_at": e.now(), "scope": "fixture"}, **options)


def test_read_back_recovers_all_rows_without_overlapping_pages():
    result = saved({"rows": [{"_id": str(i), "value": i} for i in range(51)], "complete": True})
    proof = result["evidence"]
    assert proof["coverage"]["collections"][0] == {"path": "/rows", "available": 51, "shown": 20, "omitted": 31}
    assert not proof["coverage"]["global_absence_proven"]
    offset, ids = 0, []
    while True:
        page = e.read_result(proof["result_id"], **TARGET, offset=offset, limit=9)
        for item in page["items"]:
            ids.append(item["value"]["_id"])
            assert item["evidence"]["json_pointer"] == "/rows/" + item["value"]["_id"]
        offset = page["selection"]["next_offset"]
        if offset is None:
            break
    assert ids == [str(i) for i in range(51)]


def test_projection_distinguishes_null_empty_redacted_and_absent():
    result = saved({"rows": [{"_id": "one", "empty": "", "nil": None, "password": "do-not-leak"}], "complete": True})
    read = e.read_result(result["evidence"]["result_id"], **TARGET,
                         fields=["nil", "empty", "missing", "password"], object_ids=["one"])
    assert read["items"][0]["field_states"] == {"nil": "null", "empty": "empty",
        "missing": "absent_in_saved_object", "password": "redacted"}
    assert "do-not-leak" not in json.dumps(read)
    assert read["retrieval"] == "saved_result" and not read["live_rechecked"]


def test_partial_empty_is_not_a_proof_of_absence():
    result = saved({"rows": [], "complete": False, "errors": [{"code": "page_read_failed"}]})
    assert result["evidence"]["coverage"]["status"] == "incomplete"
    assert result["evidence"]["summary"]["error_count"] == 1
    read = e.read_result(result["evidence"]["result_id"], **TARGET)
    assert read["selection"]["status"] == "not_observed_in_partial_or_unknown_result"
    assert not read["selection"]["global_absence_proven"]


def test_exhausted_offset_does_not_report_empty_dataset():
    result = saved({"rows": [{"_id": "one"}], "complete": False})
    read = e.read_result(result["evidence"]["result_id"], **TARGET, offset=1)
    assert read["selection"]["status"] == "offset_exhausted"
    assert read["selection"]["available_in_result"] == 1
    assert not read["selection"]["has_more"]


@pytest.mark.parametrize("pointer", ["rows", "/rows/~2", "/rows/~"])
def test_invalid_pointer_is_rejected(pointer):
    result = saved({"rows": []})
    with pytest.raises(ValueError, match="RFC 6901"):
        e.read_result(result["evidence"]["result_id"], **TARGET, json_pointer=pointer)


def test_missing_pointer_does_not_misreport_redacted_or_null_ancestors():
    result = saved({"object": {"credentials": {"name": "hidden"}, "empty": None, "a/b": {"~key": 42}}, "complete": True})
    rid = result["evidence"]["result_id"]
    # credentials is not necessarily a sensitive key in older client classifiers;
    # explicit password is always redacted as a whole ancestor.
    result = saved({"object": {"password": {"name": "hidden"}, "empty": None}, "complete": True})
    assert e.read_result(result["evidence"]["result_id"], **TARGET, json_pointer="/object/password/name")["selection"]["status"] == "redacted_ancestor"
    assert e.read_result(result["evidence"]["result_id"], **TARGET, json_pointer="/object/empty/name")["selection"]["status"] == "null_ancestor"
    assert e.read_result(rid, **TARGET, json_pointer="/object/a~1b/~0key")["items"][0]["value"] == 42
    assert e.read_result(rid, **TARGET, json_pointer="/missing")["selection"]["status"] == "path_absent_in_result"


def test_large_item_requires_narrowing_then_string_chunks_are_complete():
    text = "АБВ" * 10000
    result = saved({"rows": [{"_id": "one", "body": text}], "complete": True})
    rid = result["evidence"]["result_id"]
    read = e.read_result(rid, **TARGET, max_response_bytes=4096)
    assert not read["items"] and read["selection"]["status"] == "requires_narrower_selection"
    pieces, offset = [], 0
    while True:
        read = e.read_result(rid, **TARGET, json_pointer="/rows/0/body", offset=offset, text_limit=512, max_response_bytes=4096)
        assert len(json_bytes(read)) <= 4096
        pieces.append(read["items"][0]["value"])
        assert read["items"][0]["evidence"]["character_offset"] == offset
        offset = read["selection"]["next_offset"]
        if offset is None:
            break
    assert "".join(pieces) == text


def test_profile_binding_tamper_and_path_protection():
    result = saved({"rows": [{"_id": "one"}]})
    rid = result["evidence"]["result_id"]
    with pytest.raises(ValueError, match="profile/project"):
        e.read_result(rid, profile="test", project_id="other")
    with pytest.raises(ValueError):
        e.read_result("../outside", **TARGET)
    path = Path(result["presentation"]["artifact"]["path"])
    path.write_text('{"rows": []}')
    with pytest.raises(ValueError, match="integrity"):
        e.read_result(rid, **TARGET)


def test_symlink_result_is_not_followed(tmp_path):
    result = saved({"rows": []})
    path = Path(result["presentation"]["artifact"]["path"])
    outside = tmp_path / "outside.json"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink privileges unavailable")
    with pytest.raises(ValueError, match="path"):
        e.read_result(result["evidence"]["result_id"], **TARGET)


def test_full_mode_also_has_evidence_and_source_time_is_preserved():
    result = present({"rows": [], "complete": True}, response_mode="full", target=TARGET,
                     source={"mode": "snapshot", "observed_at": "2020-01-01T00:00:00+00:00"})
    assert result["presentation"]["mode"] == "full"
    read = e.read_result(result["evidence"]["result_id"], **TARGET)
    assert read["source"]["mode"] == "snapshot" and read["source"]["observed_at"].startswith("2020")


class Response:
    def __init__(self, body): self.body = body
    def as_dict(self): return {"body": self.body}


class Client:
    config = SimpleNamespace(**TARGET)
    def __init__(self):
        self.body = {"_id": "form-one", "name": "Форма", "pageTitle": "Форма", "tabs": [],
                     "description": "Управляется автоматизацией: форма учёта результатов.", "version": 1}
        self.reads, self.saves = 0, 0
    def form_full(self, _):
        self.reads += 1
        return Response(copy.deepcopy(self.body))
    def form_by_id(self, _): return Response(copy.deepcopy(self.body))
    def save_form(self, payload):
        self.saves += 1
        self.body = copy.deepcopy(payload)
        return Response({"_id": "form-one"})


def prepare(monkeypatch):
    client = Client()
    monkeypatch.setattr(tools, "_client", lambda *_: client)
    monkeypatch.setattr(views_forms, "_client", lambda *_: client)
    monkeypatch.setattr(views_forms, "_find_form", lambda *_a, **_k: copy.deepcopy(client.body))
    monkeypatch.setenv("ALTERIOS_MCP_ALLOW_WRITE", "1")
    receipt = tools.alterios_read_object_evidence(**TARGET, kind="forms", object_id="form-one")
    return client, receipt


def test_matching_evidence_allows_guarded_update_and_changed_evidence_blocks(monkeypatch):
    client, receipt = prepare(monkeypatch)
    rid = receipt["evidence"]["result_id"]
    assert tools.alterios_verify_read_evidence(**TARGET, result_id=rid)["status"] == "unchanged"
    result = views_forms.alterios_upsert_form("Форма", form_id="form-one", page_title="Новое название",
        expected_read_result_id=rid, dry_run=False, **TARGET)
    assert client.saves == 1
    assert result["response"]["read_freshness"]["live_rechecked"]
    with pytest.raises(ValueError, match="changed"):
        views_forms.alterios_upsert_form("Форма", form_id="form-one", expected_read_result_id=rid, dry_run=False, **TARGET)
    assert client.saves == 1


def test_mutation_after_planning_is_caught_before_save(monkeypatch):
    client, receipt = prepare(monkeypatch)
    original = client.form_full
    def changing(identity):
        # Evidence read was first; second read supplies planning state; third
        # immediately before save observes a concurrent change.
        if client.reads == 2:
            client.body["version"] = 2
        return original(identity)
    client.form_full = changing
    with pytest.raises(ValueError, match="changed"):
        views_forms.alterios_upsert_form("Форма", form_id="form-one", expected_read_result_id=receipt["evidence"]["result_id"], dry_run=False, **TARGET)
    assert client.saves == 0


def test_expired_evidence_and_wrong_object_fail_closed(monkeypatch):
    client, receipt = prepare(monkeypatch)
    rid = receipt["evidence"]["result_id"]
    with pytest.raises(ValueError, match="match"):
        check_freshness(client, rid, expected_kind="forms", expected_id="other")
    meta_path = Path(receipt["presentation"]["artifact"]["path"]).with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["guard"]["observed_at"] = "2000-01-01T00:00:00+00:00"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    assert check_freshness(client, rid)["status"] == "expired"
    with pytest.raises(ValueError, match="expired"):
        views_forms.alterios_upsert_form("Форма", form_id="form-one", expected_read_result_id=rid, dry_run=False, **TARGET)
    assert client.saves == 0


def test_freshness_receipt_does_not_bypass_write_gate(monkeypatch):
    client, receipt = prepare(monkeypatch)
    monkeypatch.delenv("ALTERIOS_MCP_ALLOW_WRITE")
    with pytest.raises(ControlledWriteError):
        views_forms.alterios_upsert_form("Форма", form_id="form-one", expected_read_result_id=receipt["evidence"]["result_id"], dry_run=False, **TARGET)
    assert client.saves == 0


def test_ordinary_partial_results_are_not_write_receipts():
    result = saved({"rows": [], "complete": False})
    with pytest.raises(ValueError, match="no exact-object"):
        check_freshness(Client(), result["evidence"]["result_id"])
