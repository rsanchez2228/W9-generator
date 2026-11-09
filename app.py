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

    # 2. Fast stream parsing directly from PDF directory
    if pdf_file and os.path.exists(pdf_file):
        doc = fitz.open(pdf_file)
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"
        doc.close()

        lines = [line.strip() for line in full_text.splitlines() if line.strip()]
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Match 4-digit location codes (e.g., "18 0201", "1 7073", "0201")
            m_loc = re.search(r"^\d{1,3}\s+(\d{4})$", line)
            if not m_loc:
                m_loc = re.search(r"^\d{1,3}(\d{4})$", line)
            if not m_loc:
                m_loc = re.search(r"^\b(\d{4})\b$", line)
                
            if m_loc:
                loc_code = m_loc.group(1)
                
                # Collect address lines up to City, State, ZIP
                j = i + 1
                block = []
                while j < min(i + 10, len(lines)):
                    l_curr = lines[j]
                    if re.search(r"^\d{1,3}\s+\d{4}$", l_curr) or "about:blank" in l_curr or "11/6/26" in l_curr:
                        break
                    if l_curr not in ["\uf0e0", "☑", "# LOC", "SCHOOL INFORMATION"]:
                        clean_l = re.sub(r"^[\uf0e0\u00e0\|\s]+", "", l_curr).strip()
                        if clean_l:
                            block.append(clean_l)
                    if re.search(r",\s*FL\s*\d{5}", l_curr, re.IGNORECASE):
                        break
                    j += 1
                    
                if block and re.search(r",\s*FL\s*\d{5}", block[-1], re.IGNORECASE):
                    csz = block[-1]
                    if len(block) >= 3:
                        address = block[-2]
                        name = " ".join(block[:-2]).strip()
                    elif len(block) == 2:
                        address = block[0]
                        name = ""
                    else:
                        address = ""
                        name = ""
                        
                    name = re.sub(r"^(SCHOOL INFORMATION|TELEPHONE|ADMINISTRATOR|\|\s*)+", "", name, flags=re.IGNORECASE).strip()
                    name = re.sub(r"^\d{1,3}\s+", "", name).strip()
                    
                    if loc_code not in schools and (name or address):
                        schools[loc_code] = {
                            "name": name,
                            "address": address,
                            "city_state_zip": csz
                        }
            i += 1

        # Cache extracted data to schools.csv for instant reloads
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

        # 1. Strip ALL interactive form widgets to destroy internal AcroForm links
        for widget in list(page.widgets()):
            page.delete_widget(widget)

        # 2. White-out Box 3b and Line 7 completely
        page.add_redact_annot(fitz.Rect(470, 215, 530, 255), fill=(1, 1, 1))
        page.add_redact_annot(fitz.Rect(45, 330, 300, 365), fill=(1, 1, 1))
        page.apply_redactions()

        # 3. Direct vector text placement (Static flattening)
        if box2:
            page.insert_textbox(
                fitz.Rect(45, 138, 560, 165),
                box2,
                fontsize=11,
                fontname="helv",
                color=(0, 0, 0),
                align=0,
            )

        if box5:
            page.insert_textbox(
                fitz.Rect(45, 275, 300, 305),
                box5,
                fontsize=11,
                fontname="helv",
                color=(0, 0, 0),
                align=0,
            )

        if box6:
            page.insert_textbox(
                fitz.Rect(45, 310, 300, 330),
                box6,
                fontsize=11,
                fontname="helv",
                color=(0, 0, 0),
                align=0,
            )

        if requester:
            page.insert_textbox(
                fitz.Rect(315, 275, 560, 355),
                requester,
                fontsize=7.5,
                fontname="helv",
                color=(0, 0, 0),
                align=0,
            )

        if signature_date:
            page.insert_textbox(
                fitz.Rect(410, 575, 560, 595),
                signature_date,
                fontsize=11,
                fontname="helv",
                color=(0, 0, 0),
                align=0,
            )

        # 4. Remove AcroForm root dictionary catalog
        catalog = doc.pdf_catalog()
        if doc.xref_get_key(catalog, "AcroForm")[0] != "null":
            doc.update_object(catalog, "<< /AcroForm null >>")

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
