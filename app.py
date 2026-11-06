import io
import os
from datetime import datetime
import fitz  # PyMuPDF
import streamlit as st

# Configure web page
st.set_page_config(page_title="W-9 Generator", page_icon="📄", layout="centered")

st.title("📄 School W-9 Form Generator")
st.write("Enter the required school and requester details below to generate an updated W-9 PDF.")

# Path to local master PDF template
DEFAULT_TEMPLATE_PATH = "master_w9.pdf"

# Get today's date in MM/DD/YYYY format
today_date = datetime.today().strftime("%m/%d/%Y")

# Sidebar: Optional file upload
with st.sidebar:
    st.header("Template Options")
    uploaded_file = st.file_uploader("Upload custom W-9 PDF (optional)", type=["pdf"])

# Determine which template file to use
pdf_bytes = None

if uploaded_file is not None:
    pdf_bytes = uploaded_file.read()
    st.sidebar.info("Using uploaded W-9 file.")
elif os.path.exists(DEFAULT_TEMPLATE_PATH):
    with open(DEFAULT_TEMPLATE_PATH, "rb") as f:
        pdf_bytes = f.read()
    st.success("Loaded default master W-9 template.")
else:
    st.warning("⚠️ `master_w9.pdf` not found in directory. Please upload a PDF in the sidebar or place `master_w9.pdf` in the project folder.")

# Form Input Fields
st.subheader("W-9 Field Values")
col1, col2 = st.columns(2)

with col1:
    box2 = st.text_input(
        "Box 2: Business/School Name", 
        value="", 
        placeholder="e.g. Miami Beach Senior High School"
    )
    box5 = st.text_input(
        "Box 5: Address", 
        value="", 
        placeholder="e.g. 2231 Prairie Ave"
    )
    box6 = st.text_input(
        "Box 6: City, State, ZIP", 
        value="", 
        placeholder="e.g. Miami Beach, FL 33139"
    )

with col2:
    requester = st.text_area(
        "Requester's Name and Address", 
        value="", 
        placeholder="e.g. Vendor/Company Name\n123 Business Way\nMiami, FL 33101",
        height=100
    )
    signature_date = st.text_input("Signature Date", value=today_date)

# Process PDF when button is clicked
if st.button("Generate W-9 PDF", type="primary"):
    if not pdf_bytes:
        st.error("No template available. Add `master_w9.pdf` to the folder or upload a PDF file.")
    else:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]  # First page of W-9

        # 1. Delete all interactive form widgets so the PDF becomes non-fillable (flattened)
        for widget in list(page.widgets()):
            page.delete_widget(widget)

        # 2. Target coordinates for text placement directly on page canvas
        targets = [
            {"rect": fitz.Rect(45, 140, 560, 160), "text": box2, "size": 11},            # Box 2
            {"rect": fitz.Rect(45, 280, 310, 300), "text": box5, "size": 11},            # Box 5
            {"rect": fitz.Rect(45, 315, 310, 335), "text": box6, "size": 11},            # Box 6
            {"rect": fitz.Rect(315, 280, 560, 335), "text": requester, "size": 7.5},    # Requester Box
            {"rect": fitz.Rect(410, 575, 560, 595), "text": signature_date, "size": 11}  # Signature Date (Part II)
        ]

        # 3. Bake text directly onto the document graphics layer
        for item in targets:
            if item["text"].strip():
                page.add_redact_annot(item["rect"], fill=(1, 1, 1))
                page.apply_redactions()
                page.insert_textbox(
                    item["rect"],
                    item["text"],
                    fontsize=item["size"],
                    fontname="helv",
                    color=(0, 0, 0),
                    align=0
                )

        # Output modified PDF stream
        output_buffer = io.BytesIO()
        doc.save(output_buffer)
        doc.close()
        final_pdf = output_buffer.getvalue()

        st.success("W-9 Form generated successfully!")
        
        filename = f"W9_{box2.strip().replace(' ', '_')}.pdf" if box2.strip() else "Completed_W9.pdf"
        st.download_button(
            label="📥 Download Completed W-9 PDF",
            data=final_pdf,
            file_name=filename,
            mime="application/pdf"
        )
