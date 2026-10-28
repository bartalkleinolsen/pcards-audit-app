"""OSU Purchasing Card Audit — Assignment 1, Case 2, Part IV."""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from ai_utils import MODEL, question_to_sql
from db_utils import (
    OUTPUT_ROW_LIMIT,
    SEARCH_ROW_LIMIT,
    QueryRejected,
    get_overview,
    get_year_summary,
    run_readonly_query,
    search_field,
)

st.set_page_config(page_title="OSU P-Card | Audit Workspace", page_icon="📊",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  .block-container { padding-top: 5rem; padding-bottom: 3rem; max-width: 1330px; }
  h1,h2,h3 { letter-spacing: -.035em; }
  div[data-testid="stMetric"] { background: #f7f9fc; border: 1px solid #e5ebf3;
    padding: 16px 19px; border-radius: 14px; }
  div[data-testid="stMetricLabel"] { color: #526176; font-weight: 600; }
  div[data-testid="stMetricValue"] { color: #193b5a; }
  .eyebrow { letter-spacing: .14em; font-size: .72rem; color: #4e718b;
    text-transform: uppercase; font-weight: 700; margin-bottom: .4rem; }
  .hero-sub { font-size: 1.03rem; color: #617185; margin-top: -.6rem; margin-bottom: 1.6rem; }
  .tip { background: #f5f9fe; border: 1px solid #dbe8f5; border-radius: 12px;
    padding: .9rem 1rem; color: #324b64; margin: .6rem 0 1.1rem; }
</style>
""", unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def overview():
    return get_overview()

@st.cache_data(show_spinner=False)
def year_stats(year: int):
    return get_year_summary(year)


def display_df(frame: pd.DataFrame, key: str) -> None:
    if frame.empty:
        st.info("No records matched this search. Try another keyword or year.")
        return
    config = {}
    for col in frame.columns:
        if col in ("Amount_USD", "Amount", "TotalSpent", "TotalAmount"):
            config[col] = st.column_config.NumberColumn(col.replace("_", " "), format="$%.2f")
    st.dataframe(frame, use_container_width=True, hide_index=True,
                 column_config=config, height=min(600, 50 + 35 * len(frame)))
    st.download_button("Download displayed results (CSV)",
                       data=frame.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"pcard_{key}.csv", mime="text/csv", key=f"download_{key}")


def secret(name: str, default: str = "") -> str:
    env_value = os.getenv(name)
    if env_value:
        return env_value
    try:
        return str(st.secrets.get(name, default))
    except (FileNotFoundError, KeyError):
        return default


try:
    overview_data = overview()
except Exception as exc:
    st.error(f"Could not load the P-card dataset: {exc}")
    st.stop()

st.markdown('<div class="eyebrow">Oklahoma State University · Internal Audit</div>', unsafe_allow_html=True)
st.title("P-Card Audit Workspace")
st.markdown('<div class="hero-sub">Explore purchasing-card transactions, investigate exceptions, and document higher-risk activity.</div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Audit workspace")
    st.caption("Assignment 1 · Case 2 · Part IV")
    st.divider()
    st.markdown("**Dataset**")
    st.write("Oklahoma State University")
    st.caption(f"{overview_data['transactions']:,} records · {min(overview_data['years'])}–{max(overview_data['years'])}")
    st.divider()
    st.markdown("**How to use**")
    st.markdown("1. **Ask the Database:** ask a question in plain English.\n\n"
                "2. **Prohibited Purchases:** choose a year and search descriptions or vendors.\n\n"
                "3. Inspect results and download a CSV for follow-up.")
    st.divider()
    st.caption("**Audit note**: flags are leads for investigation, not proof of fraud. "
               "Transactions may have valid explanations and must be supported by receipts and approvals.")


tab_ai, tab_search = st.tabs(["✦  Ask the Database", "⌕  Prohibited Purchases"])

with tab_ai:
    st.subheader("Ask a question about P-card spending")
    st.markdown("Ask in everyday English. Gemini prepares a read-only SQLite query; "
                "the application runs it locally and shows actual database results.")
    st.markdown("<div class='tip'>Try: <b>Who were the 10 highest-spending employees in 2014?</b> "
                "or <b>How many purchases exceeded $5,000 in 2014?</b></div>",
                unsafe_allow_html=True)
    api_key = secret("GEMINI_API_KEY")
    model_name = secret("GEMINI_MODEL", MODEL)
    if not api_key:
        st.warning("Gemini is not configured yet. The site administrator must add "
                   "GEMINI_API_KEY in Streamlit App settings → Secrets. "
                   "The Prohibited Purchases dashboard below works without an API key.")
    examples = [
        "Which 10 employees spent the most in 2014?",
        "How much was spent each month during 2014?",
        "Which vendors received the most spending in 2014?",
        "How many individual transactions exceeded $5,000 in 2014?",
    ]
    with st.form("question_form"):
        question = st.text_area("Your audit question", placeholder="Type an audit question...",
                                height=96, max_chars=1200)
        selected_example = st.selectbox("Or choose an example question", ["(Write my own)"] + examples)
        submitted = st.form_submit_button("Run analysis", type="primary",
                                          use_container_width=False, disabled=not api_key)
    if "ai_queries_used" not in st.session_state:
        st.session_state.ai_queries_used = 0
    st.caption(f"AI queries in this browser session: {st.session_state.ai_queries_used}/20. "
               "Free-tier usage limits may also apply.")
    if submitted and st.session_state.ai_queries_used >= 20:
        st.warning("Session limit reached. Open a new session later if additional queries are needed.")
    elif submitted:
        effective_question = selected_example if selected_example != "(Write my own)" else question
        if len(effective_question.strip()) < 4:
            st.warning("Enter a question first, or select an example.")
        else:
            st.session_state.ai_queries_used += 1
            with st.spinner("Generating and validating a read-only query…"):
                try:
                    sql, explanation, usage = question_to_sql(effective_question, api_key, model_name)
                    result, truncated = run_readonly_query(sql)
                except (QueryRejected, ValueError, RuntimeError) as exc:
                    st.error(f"Could not run that question: {exc}")
                    st.info("Try a shorter, more specific question. The app does not execute write operations.")
                except Exception as exc:
                    st.error(f"Gemini request failed: {exc}")
                    st.caption("Check your Streamlit Secrets and the API project's free-tier quotas.")
                else:
                    st.success("Query completed using the actual P-card database.")
                    if explanation:
                        st.write(explanation)
                    st.caption(f"Displaying {len(result)} result rows" +
                               (f" (limited to the first {OUTPUT_ROW_LIMIT})" if truncated else "") +
                               (f" · API tokens reported: {usage}" if usage is not None else ""))
                    display_df(result, "ai_results")
                    with st.expander("View the generated SQL (audit trail)"):
                        st.code(sql, language="sql")
                    st.caption("AI-generated queries can misinterpret a question. Review the SQL and "
                               "verify important findings before relying on them.")

with tab_search:
    st.subheader("Prohibited Purchases Dashboard")
    st.write("Search the transaction descriptions or vendors for purchases that may warrant "
             "follow-up under OSU P-card policies.")
    st.markdown("<div class='tip'><b>How to use:</b> Select a year, then open either "
                "Description search or Vendor search. Enter a keyword and press Search. "
                "Each search looks in its own field only. Example words include "
                "<i>gasoline</i> (description) and <i>post office</i> (vendor).</div>",
                unsafe_allow_html=True)

    year = st.selectbox("Transaction year", overview_data["years"],
                        format_func=lambda x: str(x), key="dashboard_year")
    summary = year_stats(year)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Transactions", f"{summary['transactions']:,}")
    c2.metric("Cardholders", f"{summary['employees']:,}")
    c3.metric("Vendors", f"{summary['vendors']:,}")
    c4.metric("Net spend", f"${summary['net_amount']:,.0f}")
    st.write("")
    search_description, search_vendor = st.tabs(["Description search", "Vendor search"])
    for inner_tab, field, key, placeholder in [
        (search_description, "Description", "description", "e.g. gift, gasoline, deposit"),
        (search_vendor, "Vendor", "vendor", "e.g. post office, liquor, insurance"),
    ]:
        with inner_tab:
            st.markdown(f"**Search the `{field}` field**")
            with st.form(f"{key}_search_form"):
                keyword = st.text_input(f"{field} keyword", placeholder=placeholder,
                                        max_chars=120, key=f"{key}_keyword")
                go = st.form_submit_button(f"Search {field.lower()}", type="primary")
            if go:
                if not keyword.strip():
                    st.warning("Enter a keyword before searching.")
                else:
                    try:
                        frame, total = search_field(year, field, keyword)
                    except Exception as exc:
                        st.error(f"Search failed: {exc}")
                    else:
                        st.metric("Matching transactions", f"{total:,}")
                        if total > SEARCH_ROW_LIMIT:
                            st.caption(f"Showing the {SEARCH_ROW_LIMIT} largest transactions. "
                                       "Refine the keyword to narrow your review.")
                        display_df(frame, f"{key}_{year}")
    with st.expander("What counts as a prohibited or higher-risk purchase?"):
        st.markdown("OSU policy includes alcohol, cash advances, decorations, donations, gasoline, "
                    "gifts, insurance, late fees, postage, moving expenses, personal purchases, "
                    "personal memberships, payroll, and employee awards. "
                    "Keyword matches are **not proof** of prohibited purchases. "
                    "Many source descriptions say 'GENERAL PURCHASE', so absence of a match "
                    "does **not** establish compliance.")

st.divider()
st.caption("OSU P-Card · Educational internal-audit exercise · 2010–2014 dataset supplied for the assignment. "
           "All results are preliminary audit indicators, not findings of wrongdoing.")
