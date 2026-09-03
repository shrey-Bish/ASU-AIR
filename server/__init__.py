"""SlideSight HTTP backend — wraps slidesight.remediate behind a job API.

The Streamlit frontend uploads a deck here, polls for progress, then downloads
the remediated file and report. All new code for the server lives in this
package; slidesight/ itself is untouched.
"""
