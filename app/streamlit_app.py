import os
import json
import time
import httpx
import streamlit as st

from components.upload import render_upload
from components.progress import render_progress
from components.results import render_results
from components.review_queue import render_review_queue
from components.screen_reader import render_screen_reader
from components.wcag_report import render_wcag_report
from components.downloads import render_downloads

st.set_page_config(page_title="SlideSight", page_icon="♿", layout="wide")

API_URL = os.getenv("SLIDESIGHT_API_URL", "http://localhost:8000")
DEMO_MODE = os.getenv("SLIDESIGHT_DEMO_DATA", "0") == "1"

# Session state init
if "job_status" not in st.session_state:
    st.session_state.job_status = "idle"
if "job_id" not in st.session_state:
    st.session_state.job_id = None
if "report" not in st.session_state:
    st.session_state.report = None
if "demo_mode" not in st.session_state:
    st.session_state.demo_mode = DEMO_MODE

# Global styling
st.markdown("""
<style>
.main .block-container {padding-top: 1.5rem;}
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("## SlideSight")
    st.markdown("♿")
    if st.button("New Upload", use_container_width=True):
        st.session_state.job_status = "idle"
        st.session_state.job_id = None
        st.session_state.report = None
        st.rerun()
    with st.expander("About"):
        st.write(
            "Accessibility remediation for PowerPoint lecture decks.\n\n"
            "Built for the ASU AIR Spark Challenge. Upload a .pptx, we generate alt text with confidence scoring, "
            "and return a remediated deck plus report."
        )

# Demo mode load
if st.session_state.demo_mode:
    if st.session_state.report is None:
        try:
            with open("/Users/smanika/Desktop/AIR_SPARK/fixtures/sample_report.json", "r") as f:
                st.session_state.report = json.load(f)
            st.session_state.job_status = "complete"
        except Exception as e:
            st.error(f"Failed to load demo data: {e}")
            st.session_state.demo_mode = False

# Layout
main_col, right_col = st.columns([3, 2])

with main_col:
    if st.session_state.demo_mode and st.session_state.report:
        # Show upload note
        st.info("Demo mode — showing sample results")
    
    if st.session_state.job_status == "idle" and not st.session_state.demo_mode:
        uploaded_file = render_upload(demo_mode=False)
        if uploaded_file is not None:
            # Upload to API
            try:
                with st.spinner("Uploading..."):
                    files = {
                        "file": (
                            uploaded_file.name,
                            uploaded_file.getvalue(),
                            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                        )
                    }
                    with httpx.Client(timeout=60) as client:
                        resp = client.post(f"{API_URL}/api/upload", files=files)
                        resp.raise_for_status()
                        data = resp.json()
                        job_id = data.get("job_id")
                        if not job_id:
                            st.error("No job_id returned from server")
                        else:
                            st.session_state.job_id = job_id
                            st.session_state.job_status = "processing"
                            st.rerun()
            except httpx.ConnectError:
                st.error("Server not reachable — is uvicorn running on port 8000?")
            except Exception as e:
                st.error(f"Upload failed: {e}")
    
    elif st.session_state.job_status == "processing" and not st.session_state.demo_mode:
        job_id = st.session_state.job_id
        if not job_id:
            st.error("No job_id in session")
            st.session_state.job_status = "idle"
        else:
            try:
                with httpx.Client(timeout=10) as client:
                    resp = client.get(f"{API_URL}/api/jobs/{job_id}")
                    resp.raise_for_status()
                    job_data = resp.json()
                
                status = job_data.get("status", "processing")
                if status == "complete":
                    # Fetch report
                    try:
                        r = client.get(f"{API_URL}/api/jobs/{job_id}/report")
                        r.raise_for_status()
                        st.session_state.report = r.json()
                        st.session_state.job_status = "complete"
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to fetch report: {e}")
                        st.session_state.job_status = "error"
                elif status == "error":
                    st.error("Processing failed on server")
                    st.session_state.job_status = "error"
                else:
                    render_progress(job_data)
                    time.sleep(1)
                    st.rerun()
            except httpx.ConnectError:
                st.error("Server not reachable — is uvicorn running on port 8000?")
                st.session_state.job_status = "error"
            except Exception as e:
                st.error(f"Polling error: {e}")
                st.session_state.job_status = "error"
    
    elif st.session_state.job_status == "complete" and st.session_state.report:
        render_results(st.session_state.report)
        st.divider()
        render_review_queue(st.session_state.report)
    
    elif st.session_state.job_status == "error":
        st.error("An error occurred. Try New Upload.")
    
    else:
        # idle but demo mode already handled
        if not st.session_state.demo_mode:
            uploaded_file = render_upload(demo_mode=False)

with right_col:
    if st.session_state.job_status == "complete" and st.session_state.report:
        render_screen_reader(st.session_state.report)
        st.divider()
        render_wcag_report(st.session_state.report)
        st.divider()
        render_downloads(st.session_state.job_id, st.session_state.demo_mode, API_URL)
    elif st.session_state.demo_mode and st.session_state.report:
        render_screen_reader(st.session_state.report)
        st.divider()
        render_wcag_report(st.session_state.report)
        st.divider()
        render_downloads(None, True, API_URL)
    else:
        st.info("Upload a deck to see preview, WCAG report, and downloads.")
