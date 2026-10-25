"""'Fix my weak bullets' section of the results page."""

from typing import Any, Callable, Dict

import requests
import streamlit as st

from frontend.services import api_client

_STATE_KEY = "bullet_rewrites"


def render_bullet_fixer(analysis: Dict[str, Any], on_error: Callable[[Exception], None]) -> None:
    """Show the weak bullets found in the resume and offer AI rewrites."""
    
    if "weak_bullets" not in analysis:
        st.info("Run the analysis again to get bullet suggestions.")
        return
    weak = analysis.get("weak_bullets") or []
    if not weak:
        st.caption("No weak bullets were found in your project and experience descriptions.")
        return

    bullets = [item["bullet"] for item in weak if item.get("bullet")]
    if not bullets:
        return

    st.markdown("### Fix my weak bullets")
    st.caption(
        "These bullets lost points because they do not start with a strong action verb "
        "or do not show a measurable result."
    )

    for item in weak:
        st.markdown(f"**{item.get('source', 'Resume')}** - {item.get('issues', '')}")
        st.code(item["bullet"], language=None)

    if st.button("Rewrite these with AI", type="primary", key="bullet_fixer_button"):
        try:
            with st.spinner("Rewriting your bullets..."):
                rewrites = api_client.improve_bullets(
                    bullets,
                    access_token=st.session_state["access_token"],
                )
            st.session_state[_STATE_KEY] = {"for": bullets, "rewrites": rewrites}
        except requests.RequestException as exc:
            on_error(exc)

    saved = st.session_state.get(_STATE_KEY)
    if not saved or saved.get("for") != bullets:
        return

    rewrites = saved.get("rewrites") or []
    if not rewrites:
        st.info("The AI could not improve these bullets safely. Try rewriting them by hand.")
        return

    st.markdown("#### Suggested rewrites")
    st.warning(
        "Replace every [placeholder] with a real number from your own work before you use "
        "a rewrite. Do not keep a figure you cannot back up."
    )
    for item in rewrites:
        st.caption(f"Before: {item.get('original', '')}")
        st.code(item.get("rewrite", ""), language=None)
        if item.get("note"):
            st.caption(item["note"])
