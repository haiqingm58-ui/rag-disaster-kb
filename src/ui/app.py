import math
from datetime import datetime

import pandas as pd
import pydeck as pdk
import streamlit as st

from src.ui.components import (
    display_source_status, render_chat_history, render_sidebar, render_sources,
    translate_event_type, translate_risk_level, translate_source,
)
from src.ui.diagnostics import format_embedding_error, format_llm_error
from src.ingestion.disaster_api import (
    get_last_sync_status,
    load_events_with_cache,
    sync_events_to_vectorstore,
)
from src.rag.retriever import get_last_retrieval_errors, retrieve_all
from config import DEFAULT_MAP_ZOOM
from src.rag.chain import answer_stream, get_last_usage, get_llm


@st.cache_data(ttl=300, show_spinner=False)
def _load_hazard_events(
    include_cenc: bool,
    include_usgs: bool,
    include_gdacs: bool,
    force_refresh: bool = False,
) -> tuple[list[dict], dict]:
    return load_events_with_cache(
        include_cenc=include_cenc,
        include_usgs=include_usgs,
        include_gdacs=include_gdacs,
        force_refresh=force_refresh,
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _time_filter_hours(label: str) -> int | None:
    return {
        "最近 1 小时": 1,
        "最近 24 小时": 24,
        "最近 7 天": 24 * 7,
        "全部": None,
    }.get(label)


def _apply_event_filters(events: list[dict], settings: dict) -> list[dict]:
    source_filters = set(settings.get("source_filters") or [])
    type_filters = set(settings.get("event_type_filters") or [])
    risk_filters = set(settings.get("risk_filters") or [])
    hours = _time_filter_hours(settings.get("time_filter", "全部"))
    cutoff = datetime.now().timestamp() - hours * 3600 if hours else None

    filtered = []
    for ev in events:
        if source_filters and ev.get("source") not in source_filters:
            continue
        if type_filters and ev.get("event_type_group", "Other") not in type_filters:
            continue
        if risk_filters and ev.get("risk") not in risk_filters:
            continue
        if cutoff is not None:
            ts = ev.get("time_ts")
            if not ts or ts < cutoff:
                continue
        filtered.append(ev)
    return filtered


def _df_to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def _status_markdown(statuses: dict) -> str:
    lines = []
    for source in ("CENC", "USGS", "GDACS"):
        status = statuses.get(source, {})
        if not status:
            lines.append(f"- {source}: 未启用")
            continue
        state = "成功" if status.get("success") else "失败"
        cache = "使用缓存" if status.get("used_cache") else "实时请求"
        lines.append(
            f"- {source}: {state}，{cache}，最后更新时间："
            f"{status.get('updated_at') or status.get('last_success_time') or '无'}"
        )
        if status.get("note"):
            lines.append(f"  - {status['note']}")
        if status.get("error"):
            lines.append(f"  - 失败原因：{status['error']}")
    return "\n".join(lines)


def _build_briefing_markdown(
    nearby_df: pd.DataFrame,
    all_df: pd.DataFrame,
    statuses: dict,
    settings: dict,
) -> str:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# 地质灾害简报",
        "",
        f"生成时间：{generated}",
        f"参考位置：{settings['reference_lat']:.4f}, {settings['reference_lon']:.4f}",
        f"检索半径：{settings['radius_km']} km",
        "",
        "## 附近事件",
    ]

    if nearby_df.empty:
        lines.append("当前筛选条件和半径范围内暂无事件。")
    else:
        lines.extend([
            "| 时间 | 灾种 | 地点 | 风险等级 | 距离(km) | 数据来源 |",
            "| --- | --- | --- | --- | ---: | --- |",
        ])
        for _, row in nearby_df.iterrows():
            lines.append(
                f"| {row.get('time', '')} | {row.get('event_type_cn', row.get('event_type', ''))} | "
                f"{row.get('place', '')} | {row.get('risk_cn', row.get('risk', ''))} | "
                f"{row.get('distance_km', '')} | {row.get('source_cn', row.get('source', ''))} |"
            )

    lines.extend(["", "## 高风险事件"])
    high_df = all_df[all_df["risk"].isin(["High", "Critical"])] if not all_df.empty else all_df
    if high_df.empty:
        lines.append("当前筛选条件下暂无高风险 / 严重风险事件。")
    else:
        for _, row in high_df.iterrows():
            lines.append(
                f"- {row.get('time', '')} | {row.get('event_type_cn', row.get('event_type', ''))} | "
                f"{row.get('place', '')} | {row.get('risk_cn', row.get('risk', ''))} | "
                f"{row.get('source_cn', row.get('source', ''))}"
            )

    lines.extend(["", "## 数据源状态", _status_markdown(statuses)])
    return "\n".join(lines)


def _render_map_exports(
    df: pd.DataFrame,
    nearby_df: pd.DataFrame,
    statuses: dict,
    settings: dict,
) -> None:
    st.subheader("导出")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            "导出附近灾害 CSV",
            data=_df_to_csv(nearby_df),
            file_name="nearby_geological_hazards.csv",
            mime="text/csv",
            disabled=nearby_df.empty,
        )
    with col2:
        st.download_button(
            "导出地图事件 CSV",
            data=_df_to_csv(df),
            file_name="current_map_events.csv",
            mime="text/csv",
            disabled=df.empty,
        )
    with col3:
        briefing = _build_briefing_markdown(nearby_df, df, statuses, settings)
        st.download_button(
            "导出灾害简报 Markdown",
            data=briefing.encode("utf-8"),
            file_name="geological_disaster_briefing.md",
            mime="text/markdown",
        )


def _build_chat_markdown() -> str:
    lines = ["# 灾害知识问答记录", ""]
    for msg in st.session_state.get("messages", []):
        role = "用户" if msg.get("role") == "user" else "助手"
        lines.extend([f"## {role}", "", msg.get("content", ""), ""])
    return "\n".join(lines)


def _build_sources_markdown() -> str:
    lines = ["# 检索来源", ""]
    seen = set()
    for msg in st.session_state.get("messages", []):
        for doc in msg.get("sources", []) or []:
            key = doc.page_content
            if key in seen:
                continue
            seen.add(key)
            source_label = doc.metadata.get("source_label", "[未知来源]")
            lines.extend([f"## {source_label}", "", doc.page_content, ""])
    if not seen:
        lines.append("暂无检索来源。")
    return "\n".join(lines)


def _render_chat_exports() -> None:
    if not st.session_state.get("messages"):
        return
    with st.expander("导出问答记录"):
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "导出当前问答 Markdown",
                data=_build_chat_markdown().encode("utf-8"),
                file_name="conversation.md",
                mime="text/markdown",
            )
        with col2:
            st.download_button(
                "导出检索来源 Markdown",
                data=_build_sources_markdown().encode("utf-8"),
                file_name="retrieved_sources.md",
                mime="text/markdown",
            )


def _render_usage_expander(usage: dict | None) -> None:
    """Show LLM token usage and generation speed in a collapsible section."""
    with st.expander("生成统计 / Token 用量", expanded=False):
        if not usage or usage.get("elapsed_seconds") is None:
            st.caption("暂无生成统计数据。")
            return

        elapsed = usage.get("elapsed_seconds", 0)
        col1, col2 = st.columns(2)

        with col1:
            st.metric("生成耗时", f"{elapsed:.2f} s")
            prompt_tok = usage.get("prompt_tokens")
            st.metric("输入 Token", _fmt_tok(prompt_tok))
            comp_tok = usage.get("completion_tokens")
            st.metric("输出 Token", _fmt_tok(comp_tok))
            total_tok = usage.get("total_tokens")
            st.metric("总 Token", _fmt_tok(total_tok))

        with col2:
            tps = usage.get("tokens_per_second")
            st.metric("输出速度", f"{tps:.1f} tok/s" if tps else "N/A")
            st.metric("Max Tokens", str(usage.get("max_tokens", "?")))
            st.metric("LLM 地址", usage.get("llm_base_url", "?"))

        has_token_data = (
            usage.get("prompt_tokens") is not None
            or usage.get("completion_tokens") is not None
        )
        if not has_token_data:
            st.info("当前 LLM 接口未返回 token usage，仅显示生成耗时。")


def _fmt_tok(val) -> str:
    if val is None:
        return "N/A"
    if val >= 1000:
        return f"{val / 1000:.1f}k"
    return str(val)


def _render_hazard_map(settings: dict) -> None:
    force_refresh = st.button("刷新实时灾害地图")
    if force_refresh:
        _load_hazard_events.clear()

    with st.spinner("正在加载实时地质灾害数据..."):
        events, statuses = _load_hazard_events(
            settings["enable_cenc"],
            settings["enable_usgs"],
            settings["enable_gdacs"],
            force_refresh,
        )

    display_source_status(statuses)

    if not events:
        st.warning("暂无可显示的实时灾害数据，请稍后刷新或检查网络连接。")
        return

    events = [dict(ev) for ev in events]
    if force_refresh:
        sync_result = sync_events_to_vectorstore(events)
        st.session_state["last_event_sync"] = sync_result

    sync_result = st.session_state.get("last_event_sync") or get_last_sync_status()
    if sync_result:
        st.caption(
            "实时事件同步："
            f"本次事件 {sync_result.get('total_events', 0)} 条，"
            f"新增 {sync_result.get('new_events', 0)} 条，"
            f"跳过重复 {sync_result.get('skipped_duplicates', 0)} 条，"
            f"最后同步 {sync_result.get('last_sync_time', '无')}。"
        )

    reference_lat = settings["reference_lat"]
    reference_lon = settings["reference_lon"]
    radius_km = settings["radius_km"]

    for ev in events:
        ev["distance_km"] = round(_haversine_km(reference_lat, reference_lon, ev["latitude"], ev["longitude"]), 1)

    filtered_events = _apply_event_filters(events, settings)
    if not filtered_events:
        st.info("当前筛选条件下暂无可显示的实时灾害事件，请放宽灾种、风险等级、时间范围或数据源筛选。")
        empty_df = pd.DataFrame()
        st.session_state["hazard_events_df"] = empty_df
        st.session_state["nearby_hazards_df"] = empty_df
        _render_map_exports(empty_df, empty_df, statuses, settings)
        return

    df = pd.DataFrame(filtered_events)
    df["magnitude"] = df["magnitude"].fillna("")
    df["depth_km"] = df["depth_km"].fillna("")

    # Chinese-translated columns for display
    df["event_type_cn"] = df["event_type"].apply(translate_event_type)
    df["risk_cn"] = df["risk"].apply(translate_risk_level)
    df["source_cn"] = df["source"].apply(translate_source)

    nearby_df = df[df["distance_km"] <= radius_km].sort_values(
        ["risk_score", "distance_km"],
        ascending=[False, True],
    )
    critical_count = int((df["risk_score"] >= 4).sum())
    high_count = int((df["risk_score"] >= 3).sum())

    metric_cols = st.columns(4)
    metric_cols[0].metric("当前事件总数", len(df))
    metric_cols[1].metric("附近事件数", len(nearby_df))
    metric_cols[2].metric("高风险/严重", high_count)
    metric_cols[3].metric("严重风险", critical_count)

    layers = [
        pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position="[longitude, latitude]",
            get_fill_color="color",
            get_radius="radius_m",
            radius_min_pixels=4,
            radius_max_pixels=38,
            pickable=True,
            opacity=0.78,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=pd.DataFrame([{
                "latitude": reference_lat,
                "longitude": reference_lon,
                "color": [37, 99, 235, 230],
                "radius_m": max(radius_km * 1000, 20000),
                "title": "参考位置",
                "source_cn": "用户设定",
                "event_type_cn": "参考点",
                "risk_cn": "参考",
                "source": "User Input",
                "event_type": "Reference",
                "risk": "Reference",
                "place": "",
                "time": "",
                "distance_km": 0,
            }]),
            get_position="[longitude, latitude]",
            get_fill_color="color",
            get_radius="radius_m",
            radius_min_pixels=6,
            radius_max_pixels=120,
            pickable=True,
            opacity=0.18,
        ),
    ]

    st.pydeck_chart(
        pdk.Deck(
            map_style=None,
            initial_view_state=pdk.ViewState(
                latitude=reference_lat,
                longitude=reference_lon,
                zoom=DEFAULT_MAP_ZOOM,
                pitch=0,
            ),
            layers=layers,
            tooltip={
                "html": (
                    "<b>{title}</b><br/>"
                    "数据来源：{source_cn}<br/>"
                    "灾种：{event_type_cn}<br/>"
                    "风险等级：{risk_cn}<br/>"
                    "地点：{place}<br/>"
                    "时间：{time}<br/>"
                    "距离：{distance_km} km"
                ),
                "style": {"backgroundColor": "#111827", "color": "white"},
            },
        ),
        use_container_width=True,
    )

    st.subheader("附近地质灾害")
    st.session_state["hazard_events_df"] = df
    st.session_state["nearby_hazards_df"] = nearby_df
    st.session_state["source_statuses"] = statuses

    if nearby_df.empty:
        st.info(f"{radius_km} km 范围内暂无已验证实时灾害事件。")
        _render_map_exports(df, nearby_df, statuses, settings)
        return

    display = nearby_df[[
        "risk_cn",
        "source_cn",
        "event_type_cn",
        "title",
        "place",
        "time",
        "magnitude",
        "depth_km",
        "distance_km",
        "url",
    ]]
    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        column_config={
            "risk_cn": "风险等级",
            "source_cn": "数据来源",
            "event_type_cn": "灾种",
            "title": "事件名称",
            "place": "地点",
            "time": "时间",
            "magnitude": "震级",
            "depth_km": "深度 (km)",
            "distance_km": "距离 (km)",
            "url": st.column_config.LinkColumn("来源链接"),
        },
    )
    _render_map_exports(df, nearby_df, statuses, settings)


def main():
    st.set_page_config(
        page_title="实时地质灾害信息查询系统",
        page_icon="🛰️",
        layout="wide",
    )

    settings = render_sidebar()

    st.title("实时地质灾害信息查询系统")
    st.caption(
        "基于中国地震台网（CENC）、美国地质调查局（USGS）和全球灾害预警系统（GDACS）"
        "的实时地震、洪水及相关地质灾害信息检索助手。"
    )

    _render_hazard_map(settings)

    st.divider()
    st.subheader("地质灾害知识查询")

    render_chat_history()
    _render_chat_exports()

    if prompt := st.chat_input("请输入你的问题，例如：最近有什么地震？地震时如何避险？"):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Retrieve – pass LLM for query rewriting
        with st.spinner("正在检索相关信息..."):
            llm = get_llm()
            documents = retrieve_all(
                prompt,
                enable_docs=settings["enable_docs"],
                enable_events=settings["enable_events"],
                llm=llm,
            )
            retrieval_errors = get_last_retrieval_errors()
            if retrieval_errors:
                st.warning(format_embedding_error(Exception("；".join(retrieval_errors))))

        # Generate streaming response with chat history
        with st.chat_message("assistant"):
            placeholder = st.empty()
            full_response = ""

            # Extract history (exclude sources to keep state clean)
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages[:-1]
            ]

            try:
                for chunk in answer_stream(prompt, documents, chat_history=history):
                    full_response += chunk
                    placeholder.markdown(full_response + "▌")

                if full_response.strip():
                    placeholder.markdown(full_response)
                else:
                    full_response = (
                        "抱歉，模型服务返回了空内容。请确认 llama-server 已禁用 thinking 模式，"
                        "或重启服务后再试。"
                    )
                    placeholder.warning(full_response)
            except ConnectionError:
                placeholder.error(format_llm_error(ConnectionError("无法连接到 LLM 服务")))
                full_response = "抱歉，LLM 服务未连接。"
            except Exception as e:
                placeholder.error(format_llm_error(e))
                full_response = f"抱歉，回答生成失败：{e}"

            if documents:
                render_sources(documents)

            # ── Token usage & generation stats ──
            usage = get_last_usage()
            _render_usage_expander(usage)

        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "sources": documents,
        })


if __name__ == "__main__":
    main()
