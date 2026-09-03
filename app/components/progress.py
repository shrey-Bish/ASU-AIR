import streamlit as st

def render_progress(job_data: dict):
    st.subheader("Processing...")
    
    progress = job_data.get("progress", 0)
    current_slide = job_data.get("current_slide", "?")
    total_slides = job_data.get("total_slides", "?")
    
    st.progress(int(progress))
    st.caption(f"Slide {current_slide} of {total_slides}")
    
    # Current image card
    current_img = job_data.get("current_image", {})
    if current_img:
        st.markdown("""
        <style>
        .progress-card {
            background: #1a1f2e;
            border-radius: 10px;
            padding: 16px;
            margin-top: 12px;
        }
        .badge-green {
            background: #1e3a2e;
            color: #7ed321;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
        }
        .badge-yellow {
            background: #3a2e1e;
            color: #ffd54f;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
        }
        </style>
        """, unsafe_allow_html=True)
        
        with st.container():
            st.markdown('<div class="progress-card">', unsafe_allow_html=True)
            slide_num = current_img.get("slide", "?")
            image_id = current_img.get("image_id", "")
            alt_text = current_img.get("alt_text", "")
            confidence = current_img.get("confidence", 0)
            
            st.markdown(f"**Slide {slide_num} — {image_id}**")
            st.write(alt_text or "*Generating description...*")
            
            if confidence >= 4:
                st.markdown('<span class="badge-green">✅ Auto-applied</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge-yellow">⚠️ Needs Review</span>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("Analyzing images...")
