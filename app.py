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

DEFAULT_TEMPLATE_PATH = "master_w9.pdf"
today_date = datetime.today().strftime("%m/%d/%Y")

def find_file(candidates):
    if not os.path.exists("."):
        return None
    files_in_dir = os.listdir(".")
    for candidate in candidates:
        for f in files_in_dir:
            if f.lower() == candidate.lower():
                return f
    return None

@st.cache_data
def load_schools():
    schools = {}
    csv_file = find_file(["schools.csv"])
    pdf_file = find_file(["School Directory_2.pdf", "School Directory.pdf", "school_directory.pdf"])

    # 1. Load cached CSV if available
    if csv_file and os.path.exists(csv_file):
        with open(csv_file, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                loc = str(row["location_number"]).strip().zfill(4)
                schools[loc] = {
                    "name": row["school_name"].strip(),
                    "address": row["address"].strip(),
                    "city_state_zip": row["city_state_zip"].strip(),
                }
        if len(schools) > 0:
            return schools

    # 2. Extract schools using PyMuPDF Table Finder
    if pdf_file and os.path.exists(pdf_file):
        doc = fitz.open(pdf_file)
        
        for page in doc:
            tabs = page.find_tables()
            if tabs.tables:
                table_data = tabs[0].extract()
                for row in table_data:
                    if not row or len(row) < 2:
                        continue
                    
                    loc_cell = str(row[0] or "").strip()
                    info_cell = str(row[1] or "").strip()
                    
                    # Match 4-digit location code
                    loc_match = re.search(r"\b(\d{4})\b", loc_cell)
                    if not loc_match:
                        loc_match = re.search(r"\b(\d{4})\b", info_cell)
                    
                    if loc_match and re.search(r",\s*FL\s*\d{5}", info_cell, re.IGNORECASE):
                        loc_code = loc_match.group(1)
                        
                        # Clean cell line breaks
                        lines = [l.strip() for l in info_cell.splitlines() if l.strip()]
                        
                        csz_idx = -1
                        for idx, l in enumerate(lines):
                            if re.search(r",\s*FL\s*\d{5}", l, re.IGNORECASE):
                                csz_idx = idx
                                break
                                
                        if csz_idx >= 0:
                            city_state_zip = lines[csz_idx]
                            address = lines[csz_idx - 1] if csz_idx >= 1 else ""
                            name_parts = lines[:csz_idx - 1] if csz_idx >= 2 else []
                            
                            name = " ".join(name_parts).strip()
                            name = re.sub(r"^(SCHOOL INFORMATION|TELEPHONE|ADMINISTRATOR|\|\s*|\u00e0|\uf0e0)+", "", name, flags=re.IGNORECASE).strip()
                            name = re.sub(r"^\d{1,3}\s+", "", name).strip()
                            
                            if name and address and loc_code not in schools:
                                schools[loc_code] = {
                                    "name": name,
                                    "address": address,
                                    "city_state_zip": city_state_zip,
                                }
        doc.close()

        # Cache extracted results to schools.csv
        if len(schools) > 0:
            with open("schools.csv", mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["location_number", "school_name", "address", "city_state_zip"])
                for loc, data in sorted(schools.items()):
                    writer.writerow([loc, data["name"], data["address"], data["city_state_zip"]])

    return schools

school_data = load_schools()

# Sidebar: Optional file upload
with st.sidebar:
    st.header("Template Options")
    uploaded_file = st.file_uploader("Upload custom W-9 PDF (optional)", type=["pdf"])

master_file = find_file([DEFAULT_TEMPLATE_PATH, "master_w9.pdf"])
pdf_bytes = None

if uploaded_file is not None:
    pdf_bytes = uploaded_file.read()
    st.sidebar.info("Using uploaded W-9 file.")
elif master_file and os.path.exists(master_file):
    with open(master_file, "rb") as f:
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
        page = doc[0]

        widgets = list(page.widgets())

        if widgets:
            # Delete Line 7 widget to prevent form field duplication
            for widget in widgets:
                rect = widget.rect
                if rect and 325 <= rect.y0 < 365 and rect.x0 < 300:
                    page.delete_widget(widget)

            # Populate target widgets by geometric bounds
            for widget in list(page.widgets()):
                rect = widget.rect
                if not rect:
                    continue

                if 120 <= rect.y0 < 200 and rect.x0 < 300:
                    widget.field_value = box2
                    widget.text_fontsize = 11
                    widget.update()
                elif 255 <= rect.y0 < 295 and rect.x0 < 300:
                    widget.field_value = box5
                    widget.text_fontsize = 11
                    widget.update()
                elif 295 <= rect.y0 < 325 and rect.x0 < 300:
                    widget.field_value = box6
                    widget.text_fontsize = 11
                    widget.update()
                elif 255 <= rect.y0 < 365 and rect.x0 >= 300:
                    widget.field_value = requester
                    widget.text_fontsize = 7.5
                    widget.update()
                elif 540 <= rect.y0 < 650 and rect.x0 >= 350:
                    widget.field_value = signature_date
                    widget.text_fontsize = 11
                    widget.update()
        else:
            targets = [
                {"rect": fitz.Rect(45, 140, 560, 160), "text": box2, "size": 11},
                {"rect": fitz.Rect(45, 280, 310, 300), "text": box5, "size": 11},
                {"rect": fitz.Rect(45, 315, 310, 335), "text": box6, "size": 11},
                {"rect": fitz.Rect(315, 280, 560, 335), "text": requester, "size": 7.5},
                {"rect": fitz.Rect(410, 575, 560, 595), "text": signature_date, "size": 11}
            ]
            for item in targets:
                page.add_redact_annot(item["rect"], fill=(1, 1, 1))
                page.apply_redactions()
                page.insert_textbox(item["rect"], item["text"], fontsize=item["size"], fontname="helv", color=(0, 0, 0), align=0)

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
