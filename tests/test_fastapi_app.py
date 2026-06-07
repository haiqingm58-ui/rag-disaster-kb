from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app_server.main import app


client = TestClient(app)


def auth_headers() -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health_returns_200():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"ok", "degraded"}
    assert "llm_provider" in data
    assert "graph_counts" in data
    assert "embedding_ready" in data


def test_login_returns_jwt_token():
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"].count(".") == 2
    assert data["user"]["username"] == "admin"
    assert response.cookies.get("rag_access_token")


def test_login_rejects_bad_password():
    response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401
    assert "用户名或密码错误" in response.json()["detail"]


def test_dynamic_invite_code_uses_beijing_date_rule():
    from app_server.services.invite_code_service import current_invite_code, validate_registration_invite

    assert current_invite_code(date(2026, 6, 7)) == "opengeorisk20260607"
    assert validate_registration_invite(" opengeorisk20260607 ", date(2026, 6, 7))
    assert not validate_registration_invite("opengeorisk20260606", date(2026, 6, 7))


def test_registration_requires_valid_invite(tmp_path, monkeypatch):
    from app_server.services import account_service

    monkeypatch.setattr(account_service, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(account_service, "VERIFICATION_FILE", tmp_path / "registration_codes.json")

    with TestClient(app) as isolated_client:
        response = isolated_client.post(
            "/api/auth/register/send-code",
            json={"email": "tester@example.com", "invite_code": "BAD-CODE"},
        )
    assert response.status_code == 403
    assert "邀请码无效" in response.json()["detail"]


def test_registration_email_code_creates_account_and_login(tmp_path, monkeypatch):
    from app_server.services import account_service, user_data_service
    from app_server.services.invite_code_service import current_invite_code

    sent = {}
    invite_code = current_invite_code()

    def fake_send_registration_code(email, code):
        sent["email"] = email
        sent["code"] = code

    monkeypatch.setattr(account_service, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(account_service, "VERIFICATION_FILE", tmp_path / "registration_codes.json")
    monkeypatch.setattr(user_data_service, "USER_DATA_DIR", tmp_path / "user_data")
    monkeypatch.setattr(
        account_service,
        "settings",
        replace(account_service.settings, registration_default_role="admin"),
    )
    monkeypatch.setattr(account_service, "send_registration_code", fake_send_registration_code)

    with TestClient(app) as isolated_client:
        code_response = isolated_client.post(
            "/api/auth/register/send-code",
            json={"email": "alice@example.com", "invite_code": invite_code},
        )
        assert code_response.status_code == 200
        assert code_response.json()["ok"] is True
        assert sent["email"] == "alice@example.com"

        register_response = isolated_client.post(
            "/api/auth/register",
            json={
                "username": "alice",
                "password": "AlicePass123",
                "email": "alice@example.com",
                "invite_code": invite_code,
                "verification_code": sent["code"],
            },
        )
        assert register_response.status_code == 200
        data = register_response.json()
        assert data["access_token"].count(".") == 2
        assert data["user"]["username"] == "alice"
        assert data["user"]["role"] == "admin"
        assert isolated_client.cookies.get("rag_access_token")

        login_response = isolated_client.post("/api/auth/login", json={"username": "alice", "password": "AlicePass123"})
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        save_response = isolated_client.put(
            "/api/user-data",
            headers={"Authorization": f"Bearer {token}"},
            json={"conversations": [{"id": "alice-1", "title": "账号数据", "messages": []}], "active_conversation_id": "alice-1"},
        )
        assert save_response.status_code == 200
        assert (tmp_path / "user_data" / "alice.json").exists()


def test_registration_rejects_wrong_email_code(tmp_path, monkeypatch):
    from app_server.services import account_service
    from app_server.services.invite_code_service import current_invite_code

    sent = {}
    invite_code = current_invite_code()

    def fake_send_registration_code(email, code):
        sent["code"] = code

    monkeypatch.setattr(account_service, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(account_service, "VERIFICATION_FILE", tmp_path / "registration_codes.json")
    monkeypatch.setattr(account_service, "send_registration_code", fake_send_registration_code)

    with TestClient(app) as isolated_client:
        code_response = isolated_client.post(
            "/api/auth/register/send-code",
            json={"email": "bob@example.com", "invite_code": invite_code},
        )
        assert code_response.status_code == 200
        response = isolated_client.post(
            "/api/auth/register",
            json={
                "username": "bob",
                "password": "BobPass123",
                "email": "bob@example.com",
                "invite_code": invite_code,
                "verification_code": "000000" if sent["code"] != "000000" else "111111",
            },
        )
    assert response.status_code == 400
    assert "验证码错误" in response.json()["detail"]


def test_registration_rejects_weak_password(tmp_path, monkeypatch):
    from app_server.services import account_service
    from app_server.services.invite_code_service import current_invite_code

    sent = {}

    def fake_send_registration_code(email, code):
        sent["code"] = code

    monkeypatch.setattr(account_service, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(account_service, "VERIFICATION_FILE", tmp_path / "registration_codes.json")
    monkeypatch.setattr(account_service, "send_registration_code", fake_send_registration_code)

    invite_code = current_invite_code()
    with TestClient(app) as isolated_client:
        code_response = isolated_client.post(
            "/api/auth/register/send-code",
            json={"email": "weak@example.com", "invite_code": invite_code},
        )
        assert code_response.status_code == 200
        response = isolated_client.post(
            "/api/auth/register",
            json={
                "username": "weakuser",
                "password": "weakpass123",
                "email": "weak@example.com",
                "invite_code": invite_code,
                "verification_code": sent["code"],
            },
        )
    assert response.status_code == 400
    assert "大写英文字母" in response.json()["detail"]


def test_password_reset_with_email_code_changes_password(tmp_path, monkeypatch):
    from app_server.services import account_service
    from app_server.services.invite_code_service import current_invite_code

    sent = {}

    def fake_send_registration_code(email, code):
        sent["register"] = code

    def fake_send_password_reset_code(email, code):
        sent["reset"] = code

    monkeypatch.setattr(account_service, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(account_service, "VERIFICATION_FILE", tmp_path / "registration_codes.json")
    monkeypatch.setattr(account_service, "send_registration_code", fake_send_registration_code)
    monkeypatch.setattr(account_service, "send_password_reset_code", fake_send_password_reset_code)

    invite_code = current_invite_code()
    with TestClient(app) as isolated_client:
        code_response = isolated_client.post(
            "/api/auth/register/send-code",
            json={"email": "reset@example.com", "invite_code": invite_code},
        )
        assert code_response.status_code == 200
        register_response = isolated_client.post(
            "/api/auth/register",
            json={
                "username": "resetuser",
                "password": "OldPass123",
                "email": "reset@example.com",
                "invite_code": invite_code,
                "verification_code": sent["register"],
            },
        )
        assert register_response.status_code == 200

        reset_code_response = isolated_client.post(
            "/api/auth/password-reset/send-code",
            json={"email": "reset@example.com"},
        )
        assert reset_code_response.status_code == 200
        reset_response = isolated_client.post(
            "/api/auth/password-reset",
            json={
                "email": "reset@example.com",
                "new_password": "NewPass123",
                "verification_code": sent["reset"],
            },
        )
        assert reset_response.status_code == 200
        assert reset_response.json()["ok"] is True
        old_login = isolated_client.post("/api/auth/login", json={"username": "resetuser", "password": "OldPass123"})
        assert old_login.status_code == 401
        new_login = isolated_client.post("/api/auth/login", json={"username": "resetuser", "password": "NewPass123"})
        assert new_login.status_code == 200


def test_password_reset_rejects_weak_new_password(tmp_path, monkeypatch):
    from app_server.services import account_service

    monkeypatch.setattr(account_service, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(account_service, "VERIFICATION_FILE", tmp_path / "registration_codes.json")
    response = client.post(
        "/api/auth/password-reset",
        json={"email": "missing@example.com", "new_password": "lowercase123", "verification_code": "123456"},
    )
    assert response.status_code == 400
    assert "大写英文字母" in response.json()["detail"]


def test_main_page_requires_login_cookie():
    with TestClient(app) as isolated_client:
        response = isolated_client.get("/main.html", follow_redirects=False)
    assert response.status_code in {303, 307}
    assert response.headers["location"] == "/"


def test_main_page_allows_cookie_after_login():
    with TestClient(app) as isolated_client:
        login = isolated_client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert login.status_code == 200
        response = isolated_client.get("/main.html", follow_redirects=False)
    assert response.status_code == 200
    assert "地质灾害知识图谱与智能问答系统" in response.text


def test_logout_clears_login_cookie():
    with TestClient(app) as isolated_client:
        login = isolated_client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert login.status_code == 200
        assert isolated_client.cookies.get("rag_access_token")
        response = isolated_client.post("/api/auth/logout")
        assert response.status_code == 200
        assert not isolated_client.cookies.get("rag_access_token")


def test_user_data_requires_login():
    response = client.get("/api/user-data")
    assert response.status_code == 401


def test_user_data_roundtrip(tmp_path, monkeypatch):
    from app_server.services import user_data_service

    monkeypatch.setattr(user_data_service, "USER_DATA_DIR", tmp_path)
    headers = auth_headers()
    payload = {
        "conversations": [
            {
                "id": "conv-admin-1",
                "title": "滑坡风险评估",
                "messages": [{"role": "user", "content": "滑坡风险怎么评估？"}],
            }
        ],
        "active_conversation_id": "conv-admin-1",
    }

    saved = client.put("/api/user-data", headers=headers, json=payload)
    assert saved.status_code == 200
    assert saved.json()["username"] == "admin"
    assert saved.json()["active_conversation_id"] == "conv-admin-1"

    loaded = client.get("/api/user-data", headers=headers)
    assert loaded.status_code == 200
    assert loaded.json()["conversations"][0]["title"] == "滑坡风险评估"
    assert (tmp_path / "admin.json").exists()


def test_diagnostics_requires_login():
    response = client.get("/api/diagnostics")
    assert response.status_code == 401
    assert "请先登录" in response.json()["detail"]


def test_diagnostics_returns_200_with_auth():
    response = client.get("/api/diagnostics", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert "app" in data
    assert "system" in data
    assert "config" in data


def test_diagnostics_does_not_leak_api_key():
    response = client.get("/api/diagnostics", headers=auth_headers())
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
    assert data["standards"] >= 6
    assert data["relationships"] > 0


def test_graph_search_returns_list():
    response = client.get("/api/graph/search", params={"q": "滑坡"})
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_graph_search_derived_indicator_has_node_detail():
    response = client.get("/api/graph/search", params={"q": "勘探点间距"})
    assert response.status_code == 200
    indicator = next((item for item in response.json() if item.get("type") == "指标"), None)
    assert indicator
    assert indicator["node_id"]

    detail = client.get(f"/api/graph/node/{indicator['node_id']}")
    assert detail.status_code == 200
    assert detail.json()["node"]["collection"] == "indicators"
    assert detail.json()["relations"]


def test_graph_standard_detail_exposes_child_nodes():
    response = client.get("/api/graph/standards/GB%2FT%2032864-2016")
    assert response.status_code == 200
    data = response.json()
    assert data["standard"]["code"] == "GB/T 32864-2016"
    assert data["chapters"]
    assert data["clauses"]
    assert data["indicators"]
    assert data["methods"]
    assert all(item.get("id") for item in data["indicators"])
    assert all(item.get("id") for item in data["methods"])


def test_graph_short_link_redirects_to_graph_page():
    response = client.get("/graph", follow_redirects=False)
    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/main.html#graph"


def test_chat_empty_question_returns_400():
    response = client.post("/api/chat", json={"question": "   "})
    assert response.status_code == 400
    assert "问题不能为空" in response.json()["detail"]


def test_chat_mock_llm_returns_stable_shape(monkeypatch):
    def fake_chat(question, session_id, use_graph, use_realtime, top_k, use_web=True):
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


def test_chat_accepts_web_source_shape(monkeypatch):
    def fake_chat(question, session_id, use_graph, use_realtime, top_k, use_web=True):
        assert use_web is True
        return {
            "answer": "联网增强回答",
            "sources": [{
                "type": "web",
                "title": "自然资源部地质灾害防治",
                "content": "地质灾害防治相关网页摘要",
                "source": "example.org",
                "snippet": "网页摘要",
                "url": "https://example.org/news",
            }],
            "graph_context": [],
            "realtime_events": [],
            "debug": {"web_count": 1},
        }

    monkeypatch.setattr("app_server.api.chat.run_chat", fake_chat)
    response = client.post("/api/chat", json={"question": "最近滑坡预警怎么查？"})
    assert response.status_code == 200
    data = response.json()
    assert data["sources"][0]["type"] == "web"
    assert data["sources"][0]["url"] == "https://example.org/news"
    assert data["debug"]["web_count"] == 1


def test_rag_service_uses_unified_retrieval_and_packs_evidence(monkeypatch):
    from app_server.services import rag_service

    captured = {}
    long_text = "滑坡防治工程应开展调查、监测、预警和应急处置。" * 80

    def fake_retrieve_all(query, enable_docs=True, enable_events=False, llm=None, k=None):
        captured["retrieve"] = {
            "query": query,
            "enable_docs": enable_docs,
            "enable_events": enable_events,
            "k": k,
        }
        return [Document(page_content=long_text, metadata={"filename": "规范.md", "score": 0.2})]

    def fake_answer(query, documents, chat_history=None, include_usage=False):
        captured["evidence"] = documents
        return "基于证据回答。[文档]", {"total_tokens": 10}

    monkeypatch.setattr(rag_service, "retrieve_all", fake_retrieve_all)
    monkeypatch.setattr(rag_service, "get_last_retrieval_debug", lambda: {"expanded_query": "滑坡 防治"})
    monkeypatch.setattr(rag_service, "get_last_retrieval_errors", lambda: [])
    monkeypatch.setattr(rag_service, "get_graph_service", lambda: type("Graph", (), {"context_for_question": lambda self, q, limit=5: []})())
    monkeypatch.setattr(rag_service, "events_for_question", lambda question, limit=5: [])
    monkeypatch.setattr(rag_service, "search_web", lambda question, limit=3: [])
    monkeypatch.setattr(rag_service, "answer", fake_answer)
    monkeypatch.setattr(
        rag_service,
        "settings",
        replace(rag_service.settings, rag_context_char_budget=500, rag_context_item_char_limit=180),
    )

    result = rag_service.chat("如何预防滑坡？", None, use_graph=True, use_realtime=True, top_k=4, use_web=False)

    assert captured["retrieve"] == {
        "query": "如何预防滑坡？",
        "enable_docs": True,
        "enable_events": False,
        "k": 4,
    }
    assert len(captured["evidence"]) == 1
    assert len(captured["evidence"][0].page_content) <= 183
    assert result["debug"]["retrieval"]["expanded_query"] == "滑坡 防治"
    assert result["debug"]["evidence"]["compressed_count"] == 1
    assert result["debug"]["evidence"]["evidence_chars"] <= 500


def test_documents_returns_list():
    response = client.get("/api/documents", headers=auth_headers())
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_documents_requires_login():
    response = client.get("/api/documents")
    assert response.status_code == 401


def test_upload_illegal_suffix_returns_400():
    response = client.post(
        "/api/documents/upload",
        headers=auth_headers(),
        files={"file": ("bad.exe", b"hello", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "仅支持 PDF、DOCX、PPTX、XLSX、TXT、MD" in response.json()["detail"]


def test_converter_txt_saves_markdown(tmp_path, monkeypatch):
    from app_server.services import document_converter as converter

    uploads_dir = tmp_path / "uploads"
    markdown_dir = tmp_path / "markdown"
    uploads_dir.mkdir()
    monkeypatch.setattr(converter, "UPLOADS_DIR", uploads_dir)
    monkeypatch.setattr(converter, "MARKDOWN_DIR", markdown_dir)

    source = uploads_dir / "demo.txt"
    source.write_text("滑坡监测预警要求", encoding="utf-8")
    result = converter.convert_to_markdown(source, filename="demo.txt", document_id="doc123")

    assert result.markdown_path.exists()
    assert result.markdown_path.parent == markdown_dir
    assert result.markdown_path.read_text(encoding="utf-8") == "滑坡监测预警要求"
    assert result.report["converted_to_markdown"] is True


def test_converter_rejects_path_traversal_filename():
    from app_server.services.document_converter import safe_upload_filename

    assert safe_upload_filename("../../evil.docx") == "evil.docx"


def test_converter_docx_uses_markitdown_path(tmp_path, monkeypatch):
    from app_server.services import document_converter as converter

    uploads_dir = tmp_path / "uploads"
    markdown_dir = tmp_path / "markdown"
    uploads_dir.mkdir()
    monkeypatch.setattr(converter, "UPLOADS_DIR", uploads_dir)
    monkeypatch.setattr(converter, "MARKDOWN_DIR", markdown_dir)
    monkeypatch.setattr(converter, "_markitdown_convert", lambda source: "# 转换后的 DOCX\n\n内容")

    source = uploads_dir / "demo.docx"
    source.write_bytes(b"fake-docx")
    result = converter.convert_to_markdown(source, filename="demo.docx", document_id="doc456")

    assert result.markdown_path.name == "doc456_demo.md"
    assert "转换后的 DOCX" in result.markdown_text
    assert result.report["converter"] == "markitdown"


def test_upload_docx_converts_before_ingest(tmp_path, monkeypatch):
    from app_server.services import document_service
    from app_server.services.document_converter import ConversionResult

    uploads_dir = tmp_path / "uploads"
    markdown_dir = tmp_path / "markdown"
    uploads_dir.mkdir()
    markdown_dir.mkdir()
    monkeypatch.setattr(document_service, "UPLOADS_DIR", uploads_dir)

    def fake_convert(target: Path, filename: str, document_id: str) -> ConversionResult:
        markdown_path = markdown_dir / f"{document_id}.md"
        markdown_path.write_text("# 已转换\n\n滑坡知识", encoding="utf-8")
        return ConversionResult(
            markdown_path=markdown_path,
            markdown_text="# 已转换\n\n滑坡知识",
            report={"converter": "markitdown", "converted_to_markdown": True, "markdown_path": str(markdown_path)},
        )

    captured = {}

    def fake_load_and_chunk(path: str):
        captured["loaded_path"] = path
        return [Document(page_content="滑坡知识", metadata={})], {"loader": "TextLoader", "chunk_count": 1}

    def fake_add_documents(chunks, collection):
        captured["chunks"] = chunks
        captured["collection"] = collection

    monkeypatch.setattr(document_service, "convert_to_markdown", fake_convert)
    monkeypatch.setattr(document_service, "load_and_chunk_with_report", fake_load_and_chunk)
    monkeypatch.setattr(document_service, "embedding_config_status", lambda: {"ready": True, "message": "ok"})
    monkeypatch.setattr(document_service, "add_documents", fake_add_documents)

    response = client.post(
        "/api/documents/upload",
        headers=auth_headers(),
        files={
            "file": (
                "demo.docx",
                b"fake-docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "demo.docx"
    assert data["markdown_path"].endswith(".md")
    assert captured["loaded_path"] == data["markdown_path"]
    assert captured["chunks"][0].metadata["filename"] == "demo.docx"


def test_disaster_sync_requires_login():
    response = client.post("/api/disasters/sync")
    assert response.status_code == 401


def test_firecrawl_search_normalizes_response(monkeypatch):
    from dataclasses import replace

    from app_server.services import firecrawl_service

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "data": [
                    {
                        "title": "某地暴雨洪水预警",
                        "url": "https://example.org/flood",
                        "description": "暴雨导致山洪风险升高",
                        "markdown": "正文",
                    }
                ],
            }

    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(firecrawl_service, "settings", replace(firecrawl_service.settings, firecrawl_api_key="fc-test"))
    monkeypatch.setattr(firecrawl_service.requests, "post", fake_post)

    results = firecrawl_service.search_firecrawl("洪水", limit=1)

    assert captured["url"].endswith("/v2/search")
    assert captured["headers"]["Authorization"] == "Bearer fc-test"
    assert captured["json"]["query"] == "洪水"
    assert results[0]["title"] == "某地暴雨洪水预警"
    assert results[0]["source"] == "example.org"


def test_firecrawl_web_result_to_event():
    from src.ingestion.disaster_api import _web_result_to_event

    event = _web_result_to_event(
        {
            "title": "湖南某县发布山体滑坡风险预警",
            "url": "https://example.org/landslide",
            "snippet": "连续暴雨引发山体滑坡风险，提醒群众转移避险。",
        },
        fetched_ts=1_700_000_000,
    )

    assert event
    assert event["source"] == "Firecrawl"
    assert event["event_type"] == "Landslide"
    assert event["event_uid"].startswith("realtime::firecrawl::")
    assert event["url"] == "https://example.org/landslide"


def test_disaster_sync_with_auth_uses_scheduler(monkeypatch):
    from app_server.api import disasters

    def fake_trigger(force_refresh=True, reason="manual"):
        return {
            "last_run_success": True,
            "last_result": {
                "total_events": 3,
                "new_events": 2,
                "skipped_duplicates": 1,
                "statuses": {"Firecrawl": {"configured": True, "record_count": 2}},
            },
        }

    monkeypatch.setattr(disasters.disaster_scheduler, "trigger", fake_trigger)
    response = client.post("/api/disasters/sync", headers=auth_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert data["new_events"] == 2
    assert data["statuses"]["Firecrawl"]["configured"] is True


def test_disaster_scheduler_status_requires_login():
    response = client.get("/api/disasters/scheduler")
    assert response.status_code == 401


def test_disaster_scheduler_status_with_auth():
    response = client.get("/api/disasters/scheduler", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data
    assert "interval_minutes" in data
    assert "firecrawl_configured" in data
