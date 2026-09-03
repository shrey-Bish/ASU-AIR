import streamlit as st

def _card(emoji, label, value):
    st.markdown(f"""
    <div style="
        background:#1a1f2e;
        border-radius:12px;
        padding:20px;
        text-align:center;
    ">
        <div style="font-size:28px;">{emoji}</div>
        <div style="font-size:32px;font-weight:bold;margin:8px 0;">{value}</div>
        <div style="color:#a0a0a0;font-size:14px;">{label}</div>
    </div>
    """, unsafe_allow_html=True)

def render_results(report: dict):
    # Compute stats from report
    summary = report.get("deck_summary", "")
    images_found = report.get("images_found", 0)
    auto_applied = report.get("auto_applied", 0)
    review_queue = report.get("review_queue", 0)
    decorative = report.get("decorative", 0)
    
    # Fallback compute from images list
    images = report.get("images", [])
    if not images_found and images:
        images_found = len(images)
        auto_applied = sum(1 for i in images if i.get("action") == "auto_applied")
        review_queue = sum(1 for i in images if i.get("action") == "review_queue")
        decorative = sum(1 for i in images if i.get("decorative") is True)
    
    cols = st.columns(4)
    with cols[0]:
        _card("📷", "Images Found", images_found)
    with cols[1]:
        _card("✅", "Auto-Applied", auto_applied)
    with cols[2]:
        _card("⚠️", "Needs Review", review_queue)
    with cols[3]:
        _card("⬜", "Decorative", decorative)
    
    if summary:
        with st.expander("Deck Summary", expanded=False):
            st.write(summary)
