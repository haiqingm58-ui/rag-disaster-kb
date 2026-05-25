import os
import streamlit as st
from langchain_core.documents import Document

# ── Chinese translation mappings ──────────────────────────────────────────

EVENT_TYPE_CN = {
    "Earthquake": "地震",
    "Flood": "洪水",
    "Tropical Cyclone": "热带气旋",
    "Volcano": "火山喷发",
    "Drought": "干旱",
    "Wildfire": "野火",
    "Other": "其他",
}

RISK_LEVEL_CN = {
    "Low": "低风险",
    "Moderate": "中风险",
    "High": "高风险",
    "Critical": "严重风险",
}

SOURCE_CN = {
    "CENC": "中国地震台网",
    "USGS": "美国地质调查局",
    "GDACS": "全球灾害预警系统",
}


def translate_event_type(en: str) -> str:
    return EVENT_TYPE_CN.get(en, en)


def translate_risk_level(en: str) -> str:
    return RISK_LEVEL_CN.get(en, en)


def translate_source(en: str) -> str:
    return SOURCE_CN.get(en, en)


def _translate_filter_options(options: list[str], mapping: dict) -> list[str]:
    """Return display labels for filter options, keeping original order."""
    return [mapping.get(o, o) for o in options]


def render_source_card(doc: Document) -> None:
    source_label = doc.metadata.get("source_label", "[未知来源]")
    event_type = doc.metadata.get("event_type", "")
    place = doc.metadata.get("place", "")

    subtitle_parts = [f"来源: {source_label}"]
    if event_type:
        subtitle_parts.append(f"类型: {event_type}")
    if place:
        subtitle_parts.append(f"地点: {place}")

    preview = doc.page_content[:80].replace("\n", " ")
    with st.expander(f"{source_label} {event_type} - {preview}..."):
        st.caption(" | ".join(subtitle_parts))
        st.text(doc.page_content)


def render_sources(sources: list[Document]) -> None:
    if not sources:
        st.caption("无检索到的来源")
        return

    st.caption(f"共检索到 {len(sources)} 个相关片段")
    for doc in sources:
        render_source_card(doc)


def display_source_status(statuses: dict) -> None:
    """Render realtime source health, cache freshness, and mirror notes."""
    st.subheader("数据源状态")
    if not statuses:
        st.info("尚未加载实时数据源状态。")
        return

    for source in ("CENC", "USGS", "GDACS"):
        status = statuses.get(source)
        source_cn = SOURCE_CN.get(source, source)
        if not status:
            st.caption(f"{source_cn}: 未启用")
            continue

        if status.get("success") and status.get("request_success") is True:
            headline = "请求成功"
        elif status.get("success") and status.get("used_cache"):
            headline = "当前使用缓存数据"
        else:
            headline = "请求失败"

        icon = "✅" if status.get("success") else "❌"
        cache_text = status.get("cache_time") or "无缓存"
        updated = status.get("updated_at") or status.get("last_success_time") or "无"
        count = status.get("record_count", 0)
        note = f" | {status.get('note')}" if status.get("note") else ""

        with st.expander(f"{icon} {source_cn} - {headline} ({count} 条)", expanded=False):
            st.caption(f"最后更新时间：{updated}")
            st.caption(f"缓存时间：{cache_text}")
            ttl = status.get("cache_ttl_seconds")
            age = status.get("cache_age_seconds")
            if ttl is not None and age is not None:
                st.caption(f"缓存年龄：{age:.0f}s / TTL {ttl}s")
            if status.get("used_cache"):
                st.info("当前使用缓存数据。")
            if status.get("error"):
                st.warning(f"失败原因：{status['error']}")
            if note:
                st.caption(note.strip(" |"))


def render_chat_history() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("查看来源"):
                    for doc in msg["sources"]:
                        source_label = doc.metadata.get("source_label", "[?]")
                        st.caption(f"{source_label} | {doc.page_content[:200]}...")


def render_sidebar() -> dict:
    from config import (
        LLM_PROVIDER, DEEPSEEK_API_KEY, DEEPSEEK_MODEL,
        LOCAL_LLM_BASE_URL, LOCAL_LLM_MODEL,
        OLLAMA_EMBED_MODEL, COLLECTION_DOCS, COLLECTION_EVENTS,
        DEFAULT_LATITUDE, DEFAULT_LONGITUDE, DEFAULT_RADIUS_KM,
        DEFAULT_LOCATION_NAME,
    )

    with st.sidebar:
        st.title("灾害知识检索系统")
        st.markdown("---")

        st.subheader("数据源设置")
        enable_docs = st.checkbox("本地文档检索", value=True)
        enable_events = st.checkbox("实时灾害数据", value=True)

        st.markdown("---")
        st.subheader("地图筛选")

        # Source filter with Chinese labels
        source_options = ["CENC", "USGS", "GDACS"]
        source_labels = _translate_filter_options(source_options, SOURCE_CN)
        source_display = st.multiselect(
            "数据源筛选",
            source_labels,
            default=source_labels,
        )
        source_filters = [source_options[source_labels.index(s)] for s in source_display]

        # Event type filter with Chinese labels
        event_type_options = ["Earthquake", "Flood", "Tropical Cyclone", "Volcano", "Drought", "Wildfire", "Other"]
        event_type_labels = _translate_filter_options(event_type_options, EVENT_TYPE_CN)
        event_type_display = st.multiselect(
            "灾种筛选",
            event_type_labels,
            default=event_type_labels,
        )
        event_type_filters = [event_type_options[event_type_labels.index(s)] for s in event_type_display]

        # Risk level filter with Chinese labels
        risk_options = ["Low", "Moderate", "High", "Critical"]
        risk_labels = _translate_filter_options(risk_options, RISK_LEVEL_CN)
        risk_display = st.multiselect(
            "风险等级筛选",
            risk_labels,
            default=risk_labels,
        )
        risk_filters = [risk_options[risk_labels.index(s)] for s in risk_display]

        time_filter = st.selectbox(
            "时间范围",
            ["最近 24 小时", "最近 1 小时", "最近 7 天", "全部"],
            index=0,
        )

        enable_cenc = "CENC" in source_filters
        enable_usgs = "USGS" in source_filters
        enable_gdacs = "GDACS" in source_filters

        st.markdown("---")
        st.subheader("地图定位")
        st.caption(f"默认参考位置：{DEFAULT_LOCATION_NAME}")
        reference_lat = st.number_input("纬度", min_value=-90.0, max_value=90.0, value=DEFAULT_LATITUDE, step=0.1, format="%.4f")
        reference_lon = st.number_input("经度", min_value=-180.0, max_value=180.0, value=DEFAULT_LONGITUDE, step=0.1, format="%.4f")
        radius_km = st.slider("附近半径 (km)", min_value=50, max_value=3000, value=DEFAULT_RADIUS_KM, step=50)

        st.markdown("---")
        st.subheader("文档上传")
        uploaded_files = st.file_uploader(
            "上传专业知识文档",
            type=["pdf", "txt", "md"],
            accept_multiple_files=True,
        )

        if uploaded_files:
            if st.button("导入文档到知识库", type="primary"):
                _ingest_uploaded_files(uploaded_files)

        st.markdown("---")
        st.subheader("文档管理")
        _render_doc_manager()

        st.markdown("---")
        st.subheader("操作")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("刷新实时数据"):
                _refresh_events()
        with col2:
            if st.button("清空知识库"):
                _clear_docs()

        st.markdown("---")
        st.subheader("知识库状态")
        try:
            from src.vectorstore.chroma_store import collection_count
            from config import COLLECTION_DOCS, COLLECTION_EVENTS
            docs_count = collection_count(COLLECTION_DOCS)
            events_count = collection_count(COLLECTION_EVENTS)
            st.metric("本地文档片段", docs_count)
            st.metric("实时事件记录", events_count)
        except Exception:
            st.caption("状态信息暂不可用")

        st.markdown("---")
        st.subheader("模型信息")
        if LLM_PROVIDER == "deepseek":
            st.caption("当前大模型：DeepSeek API")
            st.caption(f"模型名称：{DEEPSEEK_MODEL}")
            st.caption(f"API Key：{'已配置' if DEEPSEEK_API_KEY.strip() else '未配置'}")
        else:
            st.caption("当前大模型：本地 llama-server")
            st.caption(f"模型名称：{LOCAL_LLM_MODEL}")
            st.caption(f"模型地址：{LOCAL_LLM_BASE_URL}")
        st.caption("文档与向量库：本地 ChromaDB")
        st.caption(f"Embedding：本地 Ollama {OLLAMA_EMBED_MODEL}")

    return {
        "enable_docs": enable_docs,
        "enable_events": enable_events,
        "enable_cenc": enable_cenc,
        "enable_usgs": enable_usgs,
        "enable_gdacs": enable_gdacs,
        "source_filters": source_filters,
        "event_type_filters": event_type_filters,
        "risk_filters": risk_filters,
        "time_filter": time_filter,
        "reference_lat": reference_lat,
        "reference_lon": reference_lon,
        "radius_km": radius_km,
    }


def _render_doc_manager() -> None:
    """List uploaded documents with per-file delete buttons."""
    from src.vectorstore.chroma_store import list_sources, source_chunk_count, delete_by_source
    from config import COLLECTION_DOCS

    try:
        sources = list_sources(COLLECTION_DOCS)
    except Exception:
        st.caption("暂无法获取文档列表")
        return

    if not sources:
        st.caption("暂无已导入的文档")
        return

    for src in sources:
        name = os.path.basename(src)
        count = source_chunk_count(COLLECTION_DOCS, src)
        col1, col2 = st.columns([4, 1])
        with col1:
            st.caption(f"{name} ({count} 片段)")
        with col2:
            if st.button("删除", key=f"del_{src}"):
                delete_by_source(COLLECTION_DOCS, src)
                st.rerun()


def _ingest_uploaded_files(uploaded_files) -> None:
    import tempfile
    from pathlib import Path
    from src.ingestion.document_loader import load_and_chunk_with_report
    from src.vectorstore.chroma_store import add_documents
    from config import COLLECTION_DOCS
    from src.ui.diagnostics import format_embedding_error

    total = 0
    for f in uploaded_files:
        suffix = Path(f.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(f.getbuffer())
            tmp_path = tmp.name

        try:
            chunks, report = load_and_chunk_with_report(tmp_path)
            add_documents(chunks, COLLECTION_DOCS)
            total += len(chunks)
            if report.get("mineru_failed"):
                st.warning(
                    f"{f.name}: MinerU 解析失败，已降级 PyPDF 并成功导入。"
                    f"失败原因：{report.get('mineru_error', '')}"
                )
            else:
                st.success(f"{f.name}: 使用 {report.get('loader', 'loader')} 成功导入 {len(chunks)} 个片段")
        except Exception as e:
            report = getattr(e, "report", {})
            mineru_msg = "是" if report.get("mineru_failed") else "否"
            fallback_msg = "是" if report.get("fallback_used") else "否"
            st.error(
                f"导入 {f.name} 失败。\n\n"
                f"文件名：{f.name}\n\n"
                f"MinerU 是否失败：{mineru_msg}\n\n"
                f"是否已降级 PyPDF：{fallback_msg}\n\n"
                "最终是否成功导入：否\n\n"
                f"错误原因：{e}\n\n"
                "请确认文件未损坏；PDF 可尝试重新上传清晰版本。"
            )
            if "embed" in str(e).lower() or "ollama" in str(e).lower():
                st.error(format_embedding_error(e))
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    st.success(f"已导入 {len(uploaded_files)} 个文件，共 {total} 个片段")
    st.rerun()


def _refresh_events() -> None:
    from src.ingestion.disaster_api import sync_current_events
    with st.spinner("正在获取最新灾害数据..."):
        result = sync_current_events(force_refresh=True)
    st.success(
        "实时灾害数据同步完成："
        f"本次事件 {result['total_events']} 条，"
        f"新增 {result['new_events']} 条，"
        f"跳过重复 {result['skipped_duplicates']} 条，"
        f"最后同步 {result['last_sync_time']}。"
    )
    st.rerun()


def _clear_docs() -> None:
    from src.vectorstore.chroma_store import delete_collection
    from config import COLLECTION_DOCS
    delete_collection(COLLECTION_DOCS)
    st.success("本地知识库已清空")
    st.rerun()
