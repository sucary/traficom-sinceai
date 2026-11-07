import sys
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_SOURCE = PROJECT_ROOT / "backend" / "src"
if str(BACKEND_SOURCE) not in sys.path:
    sys.path.insert(0, str(BACKEND_SOURCE))

# The root app.py shares a module name with the backend package.
if __name__ == "app":
    __path__ = [str(BACKEND_SOURCE / "app")]

from app.rag.service import RAGService


@st.cache_resource
def get_rag_service() -> RAGService:
    """Keep the PDF index and embedding model alive between Streamlit reruns."""
    return RAGService()


def main():
    st.set_page_config(page_title="Traficom | Taajuusanalyysi", layout="wide")
    st.title("Radiotaajuuksien analyysi")
    st.markdown("Tarkastele valitun taajuuden ja palvelutyypin sääntöjä lähdeaineiston perusteella.")

    input_column, result_column = st.columns([1, 2], gap="large")

    with input_column:
        st.subheader("Analyysin tiedot")
        frequency = st.number_input(
            "Taajuus (MHz)",
            min_value=0.0,
            value=10700.0,
            step=0.1,
            format="%.3f",
        )
        service_type = st.selectbox(
            "Palvelutyyppi",
            [
                "FIXED-SATELLITE",
                "BROADCASTING-SATELLITE",
                "MOBILE-SATELLITE",
                "FIXED",
            ],
        )
        analyze = st.button("Analysoi", type="primary", use_container_width=True)

    with result_column:
        st.subheader("Analyysin tulos")

        if analyze:
            try:
                with st.spinner("Alustetaan analyysipalvelua ja lähdeaineistoa..."):
                    rag = get_rag_service()
                with st.spinner("Haetaan soveltuvia sääntöjä..."):
                    st.session_state["analysis_result"] = rag.query_rules(frequency, service_type)
                st.session_state.pop("analysis_error", None)
            except Exception as error:
                st.session_state["analysis_error"] = str(error)

        if "analysis_error" in st.session_state:
            st.error(f"Analyysi epäonnistui: {st.session_state['analysis_error']}")
        elif "analysis_result" in st.session_state:
            result = st.session_state["analysis_result"]
            if isinstance(result, dict):
                interference_risk = result.get("is_interference_risk")
                if interference_risk is True:
                    st.error("Arviossa havaittiin häiriöriski.")
                elif interference_risk is False:
                    st.success("Arviossa ei havaittu häiriöriskiä.")

                st.write("Vakavuus:", result.get("severity", "Ei ilmoitettu"))
                st.markdown("**Selitys**")
                st.write(result.get("explanation", "Ei selitystä."))

                st.markdown("**Lähdeviitteet**")
                citations = result.get("citations", [])
                if isinstance(citations, str):
                    citations = [citations] if citations else []
                for citation in citations:
                    st.markdown(f"- {citation}")

                st.text_area(
                    "Sähköpostiluonnos",
                    value=result.get("draft_email") or "",
                    height=200,
                )
            elif isinstance(result, str):
                st.write(result)
            else:
                st.error("Analyysipalvelu palautti odottamattoman vastausmuodon.")


if __name__ != "app":
    main()