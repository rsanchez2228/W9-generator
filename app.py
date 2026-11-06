import csv
import io
import os
import re
from datetime import datetime
import fitz  # PyMuPDF
import streamlit as st

# Configure web page
st.set_page_config(page_title="W-9 Generator", page_icon="📄", layout="centered")

st.title("📄 School W-9 Form Generator")
st.write("Select a school location number to auto-fill Boxes 2, 5, and 6, or type details manually.")

# File paths
DEFAULT_TEMPLATE_PATH = "master_w9.pdf"
DIRECTORY_PDF_PATH = "School Directory.pdf"
SCHOOLS_CSV_PATH = "schools.csv"

# Get today's date in MM/DD/YYYY format
today_date = datetime.today().strftime("%m/%d/%Y")

# Load and parse school directory automatically
@st.cache_data
def load_schools():
    schools = {}

    # 1. Load from generated CSV if available
    if os.path.exists(SCHOOLS_CSV_PATH):
        with open(SCHOOLS_CSV_PATH, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                loc = str(row["location_number"]).strip().zfill(4)
                schools[loc] = {
                    "name": row["school_name"].strip(),
                    "address": row["address"].strip(),
                    "city_state_zip": row["city_state_zip"].strip(),
                }
        return schools

    # 2. Parse directly from 'School Directory.pdf' if CSV does not exist
    if os.path.exists(DIRECTORY_PDF_PATH):
        doc = fitz.open(DIRECTORY_PDF_PATH)
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"
        doc.close()

        lines = [line.strip() for line in full_text.splitlines() if line.strip()]
        i = 0
        while i < len(lines):
            # Match 4-digit location code (e.g., 7073, 0201)
            if re.match(r"^\d{4}$", lines[i]):
                loc_code = lines[i]
                j = i + 1
                block = []
                while j < min(i + 12, len(lines)):
                    line = lines[j]
                    if re.match(r"^\d{4}$", line) and j > i + 1:
                        break
                    block.append(line)
                    j += 1

                # Search for city, state, and ZIP line (e.g., "MIAMI, FL 33199")
                zip_idx = -1
                for idx, b_line in enumerate(block):
                    if re.search(r",\s*FL\s*\d{5}", b_line, re.IGNORECASE):
                        zip_idx = idx
                        break

                if zip_idx >= 1:
                    city_state_zip = block[zip_idx]
                    address = block[zip_idx - 1]
                    name_lines = [
                        l for l in block[:zip_idx - 1] 
                        if not re.match(r"^\d+$", l) and not l.startswith("(") and "SCHOOL INFORMATION" not in l
                    ]
                    name = " ".join(name_lines)

                    if name and address and loc_code not in schools:
                        schools[loc_code] = {
                            "name": name,
                            "address": address,
                            "city_state_zip": city_state_zip,
                        }
            i += 1

        # Cache extracted data to CSV for faster future app startups
        if schools:
            with open(SCHOOLS_CSV_PATH, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["location_number", "school_name", "address", "city_state_zip"])
                for loc, data in schools.items():
                    writer.writerow([loc, data["name"], data["address"], data["city_state_zip"]])

    # 3. Fallback sample data if directory file is missing
    if not schools:
        schools = {
            "7121": {
                "name": "PALMETTO ELEMENTARY SCHOOL",
                "address": "12401 SW 74TH AVENUE",
                "city_state_zip": "PINECREST, FL 33156",
            },
            "7011": {
                "name": "MIAMI BEACH SHS",
                "address": "2231 PRAIRIE AVENUE",
                "city_state_zip": "MIAMI BEACH, FL 33139",
            },
        }
    return schools

school_data = load_schools()

# Sidebar: Optional file upload
with st.sidebar:
    st.header("Template Options")
    uploaded_file = st.file_uploader("Upload custom W-9 PDF (optional)", type=["pdf"])

# Determine template stream
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

# School Search Dropdown
st.subheader("1. Select School Location")

location_options = ["-- Select Location Number --"] + [
    f"{loc} - {data['name']}" for loc, data in sorted(school_data.items())
]

selected_option = st.selectbox(
    "Search by 4-Digit Location Code or School Name", 
    options=location_options
)

# Extract default values based on selection
selected_loc = selected_option.split(" - ")[0] if selected_option != "-- Select Location Number --" else None
default_info = school_data.get(selected_loc, {"name": "", "address": "", "city_state_zip": ""})

# Form Input Fields
st.subheader("2. W-9 Field Values")
col1, col2 = st.columns(2)

with col1:
    box2 = st.text_input(
        "Box 2: Business/School Name",
        value=default_info["name"],
        placeholder="e.g. MIAMI BEACH SHS",
    )
    box5 = st.text_input(
        "Box 5: Address",
        value=default_info["address"],
        placeholder="e.g. 2231 PRAIRIE AVENUE",
    )
    box6 = st.text_input(
        "Box 6: City, State, ZIP",
        value=default_info["city_state_zip"],
        placeholder="e.g. MIAMI BEACH, FL 33139",
    )

with col2:
    requester = st.text_area(
        "Requester's Name and Address",
        value="",
        placeholder="e.g. Vendor/Company Name\n123 Business Way\nMiami, FL 33101",
        height=100,
    )
    signature_date = st.text_input("Signature Date", value=today_date)

# Process PDF when button is clicked
if st.button("Generate W-9 PDF", type="primary"):
    if not pdf_bytes:
        st.error("No template available. Add `master_w9.pdf` to the folder or upload a PDF file.")
    else:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]  # First page of W-9

        widgets = list(page.widgets())

        if widgets:
            # 1. Delete Line 7 widget to prevent form field duplication
            for widget in widgets:
                rect = widget.rect
                if rect and 325 <= rect.y0 < 365 and rect.x0 < 300:
                    page.delete_widget(widget)

            # 2. Populate target widgets by geometric bounds
            for widget in list(page.widgets()):
                rect = widget.rect
                if not rect:
                    continue

                # Box 2 (Line 2): y0 between 120 and 200, left side
                if 120 <= rect.y0 < 200 and rect.x0 < 300:
                    widget.field_value = box2
                    widget.text_fontsize = 11
                    widget.update()
                # Box 5 (Line 5 - Address): y0 between 255 and 295, left side
                elif 255 <= rect.y0 < 295 and rect.x0 < 300:
                    widget.field_value = box5
                    widget.text_fontsize = 11
                    widget.update()
                # Box 6 (Line 6 - City/State/ZIP): y0 between 295 and 325, left side
                elif 295 <= rect.y0 < 325 and rect.x0 < 300:
                    widget.field_value = box6
                    widget.text_fontsize = 11
                    widget.update()
                # Requester Box: y0 between 255 and 365, right side (x0 >= 300)
                elif 255 <= rect.y0 < 365 and rect.x0 >= 300:
                    widget.field_value = requester
                    widget.text_fontsize = 7.5
                    widget.update()
                # Signature Date Box: Part II at bottom (y0 between 540 and 650, right side)
                elif 540 <= rect.y0 < 650 and rect.x0 >= 350:
                    widget.field_value = signature_date
                    widget.text_fontsize = 11
                    widget.update()
        else:
            # Fallback for flattened/non-interactive PDFs
            targets = [
                {"rect": fitz.Rect(45, 140, 560, 160), "text": box2, "size": 11},            # Box 2
                {"rect": fitz.Rect(45, 280, 310, 300), "text": box5, "size": 11},            # Box 5
                {"rect": fitz.Rect(45, 315, 310, 335), "text": box6, "size": 11},            # Box 6
                {"rect": fitz.Rect(315, 280, 560, 335), "text": requester, "size": 7.5},    # Requester Box
                {"rect": fitz.Rect(410, 575, 560, 595), "text": signature_date, "size": 11}  # Signature Date (Part II)
            ]
            for item in targets:
                page.add_redact_annot(item["rect"], fill=(1, 1, 1))
                page.apply_redactions()
                page.insert_textbox(item["rect"], item["text"], fontsize=item["size"], fontname="helv", color=(0, 0, 0), align=0)

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
            mime="application/pdf",
        )
