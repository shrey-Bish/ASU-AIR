import streamlit as st

def render_upload(demo_mode: bool):
    if demo_mode:
        st.info("Demo mode — showing sample results")
    
    # Dashed border card using markdown/CSS
    st.markdown("""
    <style>
    .upload-card {
        border: 2px dashed #4da6ff55;
        border-radius: 12px;
        padding: 48px 24px;
        text-align: center;
        background: #1a1f2e;
    }
    .upload-card p {
        color: #a0a0a0;
        margin: 8px 0 16px 0;
    }
    .badge {
        display: inline-block;
        font-size: 12px;
        padding: 4px 10px;
        border-radius: 999px;
        background: #2a3345;
        color: #8ab4f8;
        margin-top: 12px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    with st.container():
        st.markdown('<div class="upload-card">', unsafe_allow_html=True)
        st.markdown("### Drag & drop your .pptx file here")
        st.markdown("<p>or</p>", unsafe_allow_html=True)
        uploaded_file = st.file_uploader(
            "Browse files",
            type=["pptx"],
            label_visibility="collapsed",
            key="pptx_uploader"
        )
        st.markdown('<div class="badge">🔒 Processed on ASU AIR</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    
    return uploaded_file
