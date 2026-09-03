import streamlit as st

def render_screen_reader(report: dict):
    st.subheader("Screen Reader Preview")
    
    images = report.get("images", [])
    # Pick first non-decorative image with alt text
    candidate = None
    for img in images:
        if not img.get("decorative") and img.get("alt_text"):
            candidate = img
            break
    if not candidate and images:
        candidate = images[0]
    
    if not candidate:
        st.info("No images available for preview.")
        return
    
    slide = candidate.get("slide", "?")
    image_id = candidate.get("image_id", "")
    alt_text = candidate.get("alt_text", "")
    
    st.markdown(f"**Slide {slide} — {image_id}**")
    
    col_before, col_after = st.columns(2)
    
    with col_before:
        st.markdown("### Before")
        st.markdown("""
        <div style="
            background:#2a1f1f;
            border-radius:8px;
            padding:12px;
            border-left:4px solid #ff6b6b;
        ">
        <span style="color:#ff6b6b;">❌ Picture {id}</span><br>
        <span style="color:#c9c9c9;">Screen reader announces generic label</span>
        </div>
        """.format(id=image_id), unsafe_allow_html=True)
    
    with col_after:
        st.markdown("### After")
        st.markdown("""
        <div style="
            background:#1f2a1f;
            border-radius:8px;
            padding:12px;
            border-left:4px solid #7ed321;
        ">
        <span style="color:#7ed321;">✅ {alt}</span>
        </div>
        """.format(alt=alt_text or "No description"), unsafe_allow_html=True)
