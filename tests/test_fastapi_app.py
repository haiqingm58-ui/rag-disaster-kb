from __future__ import annotations

from fastapi.testclient import TestClient

from app_server.main import app


client = TestClient(app)


def test_health_returns_200():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"ok", "degraded"}
    assert "llm_provider" in data
    assert "graph_counts" in data
    assert "embedding_ready" in data


def test_diagnostics_returns_200():
    response = client.get("/api/diagnostics")
    assert response.status_code == 200
    data = response.json()
    assert "app" in data
    assert "system" in data
    assert "config" in data


def test_diagnostics_does_not_leak_api_key():
    response = client.get("/api/diagnostics")
    assert response.status_code == 200
    text = response.text.lower()
    assert "deepseek_api_key" not in text
    assert "embedding_api_key" not in text
    assert "sk-" not in text


def test_graph_summary_has_required_fields():
    response = client.get("/api/graph/summary")
    assert response.status_code == 200
    data = response.json()
    for key in ["standards", "chapters", "clauses", "terms", "requirements", "indicators", "methods"]:
        assert key in data


def test_graph_search_returns_list():
    response = client.get("/api/graph/search", params={"q": "滑坡"})
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_chat_empty_question_returns_400():
    response = client.post("/api/chat", json={"question": "   "})
    assert response.status_code == 400
    assert "问题不能为空" in response.json()["detail"]


def test_chat_mock_llm_returns_stable_shape(monkeypatch):
    def fake_chat(question, session_id, use_graph, use_realtime, top_k):
        return {
            "answer": "固定回答",
            "sources": [],
            "graph_context": [],
            "realtime_events": [],
            "debug": {"latency_ms": 1},
        }

    monkeypatch.setattr("app_server.api.chat.run_chat", fake_chat)
    response = client.post("/api/chat", json={"question": "如何预防滑坡？"})
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"answer", "sources", "graph_context", "realtime_events", "debug"}
    assert data["answer"] == "固定回答"


def test_documents_returns_list():
    response = client.get("/api/documents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_upload_illegal_suffix_returns_400():
    response = client.post(
        "/api/documents/upload",
        files={"file": ("bad.exe", b"hello", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "仅支持 PDF、TXT、MD" in response.json()["detail"]
