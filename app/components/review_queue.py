import streamlit as st

def render_review_queue(report: dict):
    images = report.get("images", [])
    queue_items = [i for i in images if i.get("action") == "review_queue"]
    
    if not queue_items:
        st.info("No items need human review.")
        return
    
    st.subheader("Human Review Queue")
    
    st.markdown("""
    <style>
    .review-card {
        background:#1a1f2e;
        border-radius:10px;
        padding:16px;
        margin-bottom:12px;
        border-left:4px solid #ffd54f;
    }
    .review-reason {
        color:#c9c9c9;
        font-style:italic;
        font-size:13px;
        margin-top:6px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    for item in queue_items:
        slide = item.get("slide", "?")
        image_id = item.get("image_id", "")
        alt_text = item.get("alt_text", "")
        reason = item.get("reason") or "Low confidence"
        
        with st.container():
            st.markdown(f'<div class="review-card">', unsafe_allow_html=True)
            st.markdown(f"**Slide {slide} — {image_id}**")
            st.write(alt_text or "*No description generated*")
            st.markdown(f'<div class="review-reason">*Low confidence: {reason}*</div>', unsafe_allow_html=True)
            
            col1, col2 = st.columns([1,1])
            with col1:
                st.button("Approve", key=f"approve_{slide}_{image_id}", disabled=True)
            with col2:
                st.button("Edit & Approve", key=f"edit_{slide}_{image_id}", disabled=True)
            st.caption("Coming soon — review workflow is deferred")
            st.markdown('</div>', unsafe_allow_html=True)
