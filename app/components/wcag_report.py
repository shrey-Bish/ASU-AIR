import streamlit as st

def render_wcag_report(report: dict):
    st.subheader("WCAG Report")
    
    wcag = report.get("wcag", {})
    total_issues = wcag.get("total_issues", 0)
    issues = wcag.get("issues", [])
    
    st.caption(f"{total_issues} issues found (not auto-fixed)")
    st.caption("These are flagged for your review — no changes were made to your deck.")
    
    if not issues:
        st.info("No WCAG issues detected.")
        return
    
    st.markdown("""
    <style>
    .wcag-issue {
        background:#1a1f2e;
        border-radius:8px;
        padding:12px;
        margin-bottom:8px;
        border-left:3px solid #4da6ff;
    }
    </style>
    """, unsafe_allow_html=True)
    
    for issue in issues:
        check = issue.get("check", "unknown")
        slide = issue.get("slide", "?")
        detail = issue.get("detail", "")
        severity = issue.get("severity", "medium")
        
        st.markdown(f'<div class="wcag-issue">', unsafe_allow_html=True)
        st.markdown(f"**Slide {slide} — {check}**  <span style='color:#a0a0a0;font-size:12px;'>[{severity}]</span>")
        st.write(detail)
        st.markdown('</div>', unsafe_allow_html=True)
