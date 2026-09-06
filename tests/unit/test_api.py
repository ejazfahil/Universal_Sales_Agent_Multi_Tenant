"""M0-9 acceptance: API surface, Article 50 disclosure, RBAC enforcement."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth.tenant import issue_token
from app.compliance.disclosure import DISCLOSURES, disclosure_for, supported_locales

TENANT = uuid.uuid4()
USER = uuid.uuid4()


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(TENANT, USER, role)}"}  # type: ignore[arg-type]


def _payload(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "message": "Where is my order?",
        "customer_ref": "cust-1",
        "locale": "en",
    }
    base.update(over)
    return base


def test_chat_requires_authentication(client: TestClient) -> None:
    assert client.post("/chat", json=_payload()).status_code == 401


def test_chat_rejects_a_forged_token(client: TestClient) -> None:
    bad = {"Authorization": "Bearer forged.signature"}
    assert client.post("/chat", json=_payload(), headers=bad).status_code == 401


def test_viewer_may_not_approve(client: TestClient) -> None:
    """RBAC: read-only roles cannot exercise oversight decisions."""
    body = {"run_id": str(uuid.uuid4()), "decision": "approve"}
    assert client.post("/approvals", json=body, headers=_auth("viewer")).status_code == 403


def test_agent_may_approve(client: TestClient) -> None:
    body = {"run_id": str(uuid.uuid4()), "decision": "approve"}
    r = client.post("/approvals", json=body, headers=_auth("agent"))
    assert r.status_code == 201
    assert r.json()["executed"] is True


def test_deny_does_not_execute(client: TestClient) -> None:
    body = {"run_id": str(uuid.uuid4()), "decision": "deny", "reason": "wrong policy"}
    r = client.post("/approvals", json=body, headers=_auth("agent"))
    assert r.json()["executed"] is False


def test_edit_requires_a_draft(client: TestClient) -> None:
    body = {"run_id": str(uuid.uuid4()), "decision": "edit"}
    assert client.post("/approvals", json=body, headers=_auth("agent")).status_code == 422


def test_bulk_records_each_run_individually(client: TestClient) -> None:
    """Bulk is operator convenience, never a weakening of the gate."""
    run_ids = [str(uuid.uuid4()) for _ in range(3)]
    r = client.post(
        "/approvals/bulk",
        json={"run_ids": run_ids, "decision": "approve"},
        headers=_auth("agent"),
    )
    assert r.status_code == 200
    assert len(r.json()) == 3
    assert {row["run_id"] for row in r.json()} == set(run_ids)


@pytest.mark.parametrize("locale", sorted(DISCLOSURES))
def test_every_conversation_opens_with_a_localised_disclosure(
    client: TestClient, locale: str
) -> None:
    """★ Invariant I7 / AI Act Art. 50(1) and 50(5)."""
    r = client.post("/chat", json=_payload(locale=locale), headers=_auth("agent"))
    assert r.status_code == 200
    assert r.json()["disclosure"] == DISCLOSURES[locale]
    assert r.json()["disclosure"].strip() != ""


def test_disclosure_falls_back_to_base_language() -> None:
    assert disclosure_for("de-AT") == DISCLOSURES["de"]
    assert disclosure_for("zz") == DISCLOSURES["en"]


def test_ten_eu_locales_supported() -> None:
    assert len(supported_locales()) >= 10


def test_chat_surfaces_the_weakest_signal_not_just_a_score(client: TestClient) -> None:
    """Automation-bias mitigation, Art. 14(4)."""
    r = client.post("/chat", json=_payload(), headers=_auth("agent")).json()
    assert "weakest_signal" in r
    assert set(r["confidence_components"]) >= {
        "confidence",
        "retrieval_score",
        "grounding_score",
        "policy_match_score",
        "novelty_score",
    }


def test_ungrounded_reply_is_not_delivered(client: TestClient) -> None:
    r = client.post("/chat", json=_payload(), headers=_auth("agent")).json()
    assert r["delivered"] is False
    assert r["decision"] in ("require_approval", "escalate")


def test_policy_endpoint_states_money_is_always_gated(client: TestClient) -> None:
    r = client.get("/chat/policy", headers=_auth("agent")).json()
    assert r["money_always_gated"] is True
    assert r["emotion_inference"] is False


def test_erasure_scope_covers_vectors_and_vault(client: TestClient) -> None:
    """Erasure that stops at relational rows is not erasure."""
    r = client.get("/gdpr/erasure-scope", headers=_auth("agent")).json()
    assert "vector_chunks" in r["deleted_from"]
    assert "token_vault" in r["deleted_from"]
    assert r["retained"] == ["audit_logs"]
