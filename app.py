import streamlit as st
from backend.run_analysis import run_joern_pipeline
from backend.graph_loader import load_graph
import networkx as nx
import matplotlib.pyplot as plt
from backend.compile_runtime import run_compile_pipeline

st.set_page_config(page_title="CVD-MAX", layout="wide")

# ---------------- STATE ----------------
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False

if "saved" not in st.session_state:
    st.session_state.saved = False

if "code" not in st.session_state:
    st.session_state.code = ""


# ---------------- STYLING ----------------
st.markdown("""
<style>
body { background-color: #0e1117; color: white; }
.stApp { background-color: #0e1117; }

textarea {
    background-color: #161b22 !important;
    color: #ffffff !important;
    font-family: monospace;
    border-radius: 12px !important;
    border: 1px solid #30363d !important;
    padding: 15px !important;
}

button {
    background-color: #007acc !important;
    color: white !important;
    border-radius: 8px !important;
}

.block-container {
    padding-top: 2rem;
}
</style>
""", unsafe_allow_html=True)


# ---------------- HEADER ----------------
st.markdown("""
<h1 style='text-align: center; color: #58a6ff;'>CVD-MAX</h1>
<p style='text-align: center; color: #8b949e;'>
Real-time C/C++ Vulnerability Detection Interface
</p>
""", unsafe_allow_html=True)


# ---------------- LABEL ----------------
st.markdown("#### Enter your C/C++ code below:")


# ---------------- EDITOR ----------------
code = st.text_area(
    "",
    height=350,
    value=st.session_state.code,
    key="code_input"
)

st.session_state.code = code


# ---------------- BUTTONS ----------------
col1, col2 = st.columns(2)

with col1:
    check = st.button("Check Vulnerability")

with col2:
    st.download_button(
        "Download .c",
        data=st.session_state.code,
        file_name="user_code.c",
        mime="text/plain"
    )


# ---------------- LOGIC ----------------
if check:
    if st.session_state.code.strip() == "":
        st.error("Please enter code first.")
    else:
        with open("workspace/input/user_code.c", "w") as f:
            f.write(st.session_state.code)

        with st.spinner("Running analysis..."):
            try:
                run_joern_pipeline()
                run_compile_pipeline()
                st.session_state.analysis_done = True
                st.session_state.saved = True
            except Exception as e:
                st.error(f"Error: {e}")


# ---------------- RESULT ----------------
if st.session_state.analysis_done:
    st.success("Code saved successfully")

    st.markdown("""
    <div style="background-color:#161b22;padding:15px;border-radius:10px;border:1px solid #30363d;margin-top:10px;">
    <b>Analysis Result:</b><br>
    Waiting for model integration...
    </div>
    """, unsafe_allow_html=True)


# ---------------- PREVIEW ----------------
st.markdown("---")
st.subheader("Code Preview")
st.code(st.session_state.code, language="cpp")

# ---------------- GRAPH DISPLAY ----------------
def draw_graph(data_list, title):
    if not data_list:
        st.warning(f"{title} not available")
        return

    st.subheader(title)

    for data in data_list:

        if not isinstance(data, dict):
            continue
        if "edges" not in data:
            continue

        G = nx.DiGraph()

        for edge in data["edges"]:
            if "source" in edge and "target" in edge:
                G.add_edge(edge["source"], edge["target"])

        if len(G.nodes) == 0:
            continue

        plt.figure(figsize=(6, 4))
        pos = nx.spring_layout(G, k=0.15)
        nx.draw(G, pos, with_labels=False, node_size=50)

        st.pyplot(plt)


if st.session_state.analysis_done:
    cfg = load_graph("cfg")
    pdg = load_graph("pdg")
    ast = load_graph("ast")

    draw_graph(cfg, "CFG Graph")
    draw_graph(pdg, "PDG Graph")
    draw_graph(ast, "AST Graph")