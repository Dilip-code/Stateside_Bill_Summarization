import os
import requests
import pandas as pd
from pdf2image import convert_from_path
import pytesseract
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from together import Together
import streamlit as st
import io

load_dotenv()
together_api_key = os.getenv("TOGETHER_AI_API_KEY")
client = Together(api_key=together_api_key)

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  


def clean_summary(text):
    """Cleans the summary by removing instructions and markdown-style bold formatting."""
    if not text:
        return ""

    # List of instruction phrases to remove
    instruction_phrases = [
        "Here is a 2-paragraph extractive summary of the text:",
        "Here is a 2-paragraph abstractive summary of the provided text:",
        "Here are the highlights in 15-20 bullet points under 4 headings:",
        "Here is a 2-paragraph abstractive summary of the text:"
    ]

    # Remove instruction phrases at the beginning
    for phrase in instruction_phrases:
        if text.startswith(phrase):
            text = text[len(phrase):].lstrip()

    # Remove markdown-like bold formatting (**text**)
    text = text.replace("**", "").replace("### ", "")

    return text.strip()



def ensure_folder_exists(folder_name):
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

def download_pdf_from_url(url, output_folder):
    try:
        ensure_folder_exists(output_folder)  # Ensure folder exists before saving
        
        response = requests.get(url, stream=True)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")

        print(f"Downloading {url}, Content-Type: {content_type}")  # Debugging

        if "application/pdf" not in content_type and not url.lower().endswith(".pdf"):
            print(f"Skipping non-PDF URL: {url}")
            return None

        pdf_name = url.split("/")[-1] or "downloaded_pdf.pdf"
        pdf_path = os.path.join(output_folder, pdf_name)
        
        with open(pdf_path, "wb") as pdf_file:
            for chunk in response.iter_content(chunk_size=8192):
                pdf_file.write(chunk)
        
        print(f"PDF saved at {pdf_path}")  # Debugging
        return pdf_path
    except Exception as e:
        print(f"Error downloading PDF: {e}")  # Debugging
        return None


def convert_pdf_to_images(pdf_path, output_folder):
    try:
        ensure_folder_exists(output_folder)  # Ensure output folder exists
        poppler_path = r"C:\\Release-24.08.0-0\\poppler-24.08.0\\Library\\bin"

        print(f"Converting PDF to images: {pdf_path}")  # Debugging
        
        if not os.path.exists(pdf_path):
            print(f"PDF file does not exist: {pdf_path}")
            return [], 0

        pages = convert_from_path(pdf_path, poppler_path=poppler_path)

        image_paths = []
        for i, page in enumerate(pages):
            image_path = os.path.join(output_folder, f"{os.path.basename(pdf_path)}_page_{i + 1}.jpg")
            page.save(image_path, "JPEG")
            image_paths.append(image_path)

        print(f"Converted {len(image_paths)} pages to images")  # Debugging
        return image_paths, len(pages)

    except Exception as e:
        print(f"Error converting PDF to images: {e}")  # Debugging
        return [], 0

def extract_text_from_image(image_path):
    try:
        return pytesseract.image_to_string(image_path, config='--psm 6')
    except Exception as e:
        return ""

def extract_text_from_webpage(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        return soup.get_text(separator=" ")
    except Exception as e:
        return ""

def query_together_ai(prompt):
    """Generates a summary using Together AI and cleans it before returning."""
    try:
        response = client.chat.completions.create(
            model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
            messages=[{"role": "user", "content": prompt}],
            stream=True
        )
        result = ""
        for token in response:
            if hasattr(token, 'choices'):
                result += token.choices[0].delta.content
        
        return clean_summary(result)  # Clean summary before returning
    except Exception as e:
        return None


def generate_summaries_with_together_ai(combined_text, num_pages):
    extractive_prompt = f"Generate an extractive summary with {min(num_pages, 4)} paragraphs:\n\n{combined_text}"
    abstractive_prompt = f"Generate an abstractive summary in 2 paragraphs:\n\n{combined_text}"
    highlights_prompt = f"Generate highlights in 15-20 bullet points under 4 headings:\n\n{combined_text}"
    
    extractive = query_together_ai(extractive_prompt)
    abstractive = query_together_ai(abstractive_prompt)
    highlights = query_together_ai(highlights_prompt)

    return extractive, abstractive, highlights


st.title("Stateside Bill Summarization")

option = st.radio("Choose an option:", ("Upload a PDF", "Input a website link", "Upload an Excel file"))

if option == "Upload a PDF":
    uploaded_pdf = st.file_uploader("Upload a PDF file", type=["pdf"])
    if uploaded_pdf:
        uploads_folder = "uploads"
        ensure_folder_exists(uploads_folder)
        images_folder = "images"
        ensure_folder_exists(images_folder)
        
        pdf_path = os.path.join(uploads_folder, uploaded_pdf.name)
        with open(pdf_path, "wb") as f:
            f.write(uploaded_pdf.read())
        
        image_paths, num_pages = convert_pdf_to_images(pdf_path, images_folder)
        if image_paths:
            all_text = "".join([extract_text_from_image(img) for img in image_paths])
            summaries = generate_summaries_with_together_ai(all_text, num_pages)
            st.subheader("Extractive Summary")
            st.write(summaries[0])
            st.subheader("Abstractive Summary")
            st.write(summaries[1])
            st.subheader("Highlights and Analysis")
            st.write(summaries[2])

elif option == "Input a website link":
    url = st.text_input("Enter the URL:")
    if url:
        if url.lower().endswith(".pdf"):  # PDF Link
            downloads_folder = "downloads"
            ensure_folder_exists(downloads_folder)
            images_folder = "images"
            ensure_folder_exists(images_folder)

            pdf_path = download_pdf_from_url(url, downloads_folder)
            if pdf_path:
                image_paths, num_pages = convert_pdf_to_images(pdf_path, images_folder)
                if image_paths:
                    all_text = "".join([extract_text_from_image(img) for img in image_paths])
                    summaries = generate_summaries_with_together_ai(all_text, num_pages)
                    st.subheader("Extractive Summary")
                    st.write(summaries[0])
                    st.subheader("Abstractive Summary")
                    st.write(summaries[1])
                    st.subheader("Highlights and Analysis")
                    st.write(summaries[2])
                else:
                    st.error("Could not extract text from the PDF.")
            else:
                st.error("Failed to download the PDF.")
        else:  # Webpage Link
            webpage_text = extract_text_from_webpage(url)
            if webpage_text.strip():
                summaries = generate_summaries_with_together_ai(webpage_text, 3)
                st.subheader("Extractive Summary")
                st.write(summaries[0])
                st.subheader("Abstractive Summary")
                st.write(summaries[1])
                st.subheader("Highlights and Analysis")
                st.write(summaries[2])
            else:
                st.error("Failed to extract text from the webpage.")

if "summary_df" not in st.session_state:
    st.session_state.summary_df = None  # Store summaries
if "excel_buffer" not in st.session_state:
    st.session_state.excel_buffer = None  # Store Excel file

elif option == "Upload an Excel file":
    uploaded_excel = st.file_uploader("Upload an Excel file", type=["xlsx"])
    
    if uploaded_excel and st.session_state.summary_df is None:  # Avoid reprocessing
        df = pd.read_excel(uploaded_excel)
        
        if "BillTextURL" in df.columns:
            if "BillState" not in df.columns:
                df["BillState"] = "Unknown"  # Default if missing
            
            results = []  # Store processed results
            
            for index, row in df.iterrows():
                url = str(row["BillTextURL"]).strip()
                bill_state = row["BillState"]
                
                abstractive_summary, extractive_summary, highlights_summary = "", "", ""

                if url.lower().endswith(".pdf"):  # PDF URL
                    pdf_path = download_pdf_from_url(url, "downloads")
                    
                    if pdf_path:
                        image_paths, num_pages = convert_pdf_to_images(pdf_path, "images")
                        
                        if image_paths:
                            all_text = "".join([extract_text_from_image(img) for img in image_paths])
                            summaries = generate_summaries_with_together_ai(all_text, num_pages)
                            
                            extractive_summary = clean_summary(summaries[0]) or "N/A"
                            abstractive_summary = clean_summary(summaries[1]) or "N/A"
                            highlights_summary = clean_summary(summaries[2]) or "N/A"
                
                else:  # Webpage URL
                    webpage_text = extract_text_from_webpage(url)
                    
                    if webpage_text.strip():
                        summaries = generate_summaries_with_together_ai(webpage_text, 3)
                        
                        extractive_summary = clean_summary(summaries[0]) or "N/A"
                        abstractive_summary = clean_summary(summaries[1]) or "N/A"
                        highlights_summary = clean_summary(summaries[2]) or "N/A"
                
                results.append({
                    "BillState": bill_state,
                    "BillTextURL": url,
                    "Extractive Summary": extractive_summary,
                    "Abstractive Summary": abstractive_summary,
                    "Highlights and Analysis": highlights_summary
                })

            # Store results in session_state
            st.session_state.summary_df = pd.DataFrame(results)

            # Save to Excel in-memory
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
                st.session_state.summary_df.to_excel(writer, index=False, sheet_name="Summaries")
            excel_buffer.seek(0)
            
            # Store the file in session state
            st.session_state.excel_buffer = excel_buffer

    # Once the summaries are generated, show download button
    if st.session_state.summary_df is not None and st.session_state.excel_buffer is not None:
        st.download_button(
            label="Download Summary Excel",
            data=st.session_state.excel_buffer,
            file_name="Summarized_Bills.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
