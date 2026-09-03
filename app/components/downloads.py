import streamlit as st
import httpx

def render_downloads(job_id: str, demo_mode: bool, api_url: str):
    st.subheader("Downloads")
    
    if demo_mode:
        st.info("Download unavailable in demo mode")
        st.button("📥 Download Remediated Deck (.pptx)", disabled=True)
        st.button("📄 Download Accessibility Report (JSON)", disabled=True)
        return
    
    if not job_id:
        st.warning("No active job to download.")
        return
    
    # Download remediated deck
    try:
        with httpx.Client(timeout=60) as client:
            # Fetch deck
            resp = client.get(f"{api_url}/api/jobs/{job_id}/download")
            resp.raise_for_status()
            deck_bytes = resp.content
            deck_name = f"remediated_{job_id}.pptx"
            
            st.download_button(
                label="📥 Download Remediated Deck (.pptx)",
                data=deck_bytes,
                file_name=deck_name,
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                use_container_width=True
            )
    except Exception as e:
        st.error(f"Failed to fetch deck: {e}")
    
    # Download report
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{api_url}/api/jobs/{job_id}/report")
            resp.raise_for_status()
            report_bytes = resp.content
            report_name = f"report_{job_id}.json"
            
            st.download_button(
                label="📄 Download Accessibility Report (JSON)",
                data=report_bytes,
                file_name=report_name,
                mime="application/json",
                use_container_width=True
            )
    except Exception as e:
        st.error(f"Failed to fetch report: {e}")
