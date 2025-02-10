import streamlit as st
import requests
from bs4 import BeautifulSoup
import os
from pdf2image import convert_from_path
import pytesseract
import openai
from bs4 import BeautifulSoup as BS

from dotenv import load_dotenv
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

openai.api_key = openai_api_key

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def ensure_folder_exists(folder_name):
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

def convert_pdf_to_images(pdf_path, output_folder):
    try:
        pages = convert_from_path(pdf_path)
        image_paths = []
        for i, page in enumerate(pages):
            image_path = os.path.join(output_folder, f"{os.path.basename(pdf_path)}_page_{i + 1}.jpg")
            page.save(image_path, "JPEG")
            image_paths.append(image_path)
        return image_paths, len(pages)  
    except Exception as e:
        st.error(f"Failed to convert PDF to images: {e}")
        return [], 0

def extract_text_from_image(image_path):
    try:
        text = pytesseract.image_to_string(image_path, config='--psm 6')  
        return text
    except Exception as e:
        st.error(f"Failed to extract text from image: {e}")
        return None

def process_text_with_gpt(text, prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": f"{prompt}\n\n{text}"}]
        )
        html_content = response['choices'][0]['message']['content']
        return html_content
    except Exception as e:
        st.error(f"Error processing text with GPT: {e}")
        return None

def html_to_json(html_content):
    try:
        soup = BS(html_content, "html.parser")
        json_data = []
        paragraph_count = 0
        for idx, section in enumerate(soup.find_all(['h1', 'h2', 'p'])):
            text_type = None
            heading_text = None
            paragraph_text = None

            if section.name == 'h1':
                heading_text = section.get_text(strip=True)
                text_type = 'heading'
            elif section.name == 'h2':
                heading_text = section.get_text(strip=True)
                text_type = 'heading' 
            elif section.name == 'p':
                paragraph_count += 1
                paragraph_text = section.get_text(strip=True)
                text_type = 'paragraph'

            # Create the JSON structure
            json_data.append({
                "heading_identifier": heading_text if text_type == 'heading' else None,
                "heading_text": heading_text,
                "text_type": text_type,
                "text": paragraph_text if text_type == 'paragraph' else None
            })
        return json_data
    except Exception as e:
        st.error(f"Failed to convert HTML to JSON: {e}")
        return []

def generate_summaries(combined_text, num_pages):
    if num_pages == 4:
        extractive_paragraph_limit = 4
        abstractive_paragraph_limit = 2
    else:
        extractive_paragraph_limit = num_pages  
        abstractive_paragraph_limit = 2  

    extractive_prompt = f"Generate an extractive summary of the following text with {extractive_paragraph_limit} paragraphs:\n\n{combined_text}"

    abstractive_prompt = f"Generate an abstractive summary of the following text in {abstractive_paragraph_limit} paragraphs:\n\n{combined_text}"

    highlights_prompt = f"Generate highlights and analysis of the following text. Provide a maximum of 15-20 bullet points divided under 4 broad headings:\n\n{combined_text}"

    try:
        extractive_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": extractive_prompt}]
        )
        extractive_summary = extractive_response['choices'][0]['message']['content']
        
        abstractive_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": abstractive_prompt}]
        )
        abstractive_summary = abstractive_response['choices'][0]['message']['content']

        highlights_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": highlights_prompt}]
        )
        highlights_summary = highlights_response['choices'][0]['message']['content']

        return extractive_summary, abstractive_summary, highlights_summary
    except Exception as e:
        st.error(f"Error generating summaries: {e}")
        return None, None, None

def scrape_and_download_pdfs(url, prompt):
    try:
        downloads_folder = "downloads"
        ensure_folder_exists(downloads_folder)
        images_folder = "images"
        ensure_folder_exists(images_folder)

        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        relevant_section = soup.find("span", class_="file_uploads_title", string="Relevant Links")
        if relevant_section:
            pdf_list_section = relevant_section.find_next("div", class_="relevant_links_s")
            if pdf_list_section:
                pdf_links = pdf_list_section.find("ul", class_="pdf_html_links").find_all("a")
                if pdf_links:
                    st.success(f"Found {len(pdf_links)} PDF(s). Processing...")
                    for idx, pdf_link in enumerate(pdf_links):
                        pdf_url = requests.compat.urljoin(url, pdf_link["href"])
                        pdf_name = pdf_link.text.strip() or f"downloaded_pdf_{idx + 1}.pdf"
                        pdf_response = requests.get(pdf_url)
                        local_pdf_path = os.path.join(downloads_folder, f"{pdf_name.replace(' ', '_')}.pdf")
                        with open(local_pdf_path, "wb") as pdf_file:
                            pdf_file.write(pdf_response.content)
                        
                        image_paths, num_pages = convert_pdf_to_images(local_pdf_path, images_folder)
                        if image_paths:
                            all_text = ""
                            for image_path in image_paths:
                                extracted_text = extract_text_from_image(image_path)
                                if extracted_text:
                                    all_text += extracted_text  
                                    
                            if all_text:
                                html_content = process_text_with_gpt(all_text, prompt)
                                if html_content:
                                    json_data = html_to_json(html_content)
                                    combined_text = " ".join([entry['text'] for entry in json_data if entry['text']])
                                    extractive_summary, abstractive_summary, highlights_summary = generate_summaries(combined_text, num_pages)
                                    
                                    st.subheader("Extractive Summary")
                                    st.write(extractive_summary)
                                    
                                    st.subheader("Abstractive Summary")
                                    st.write(abstractive_summary)

                                    st.subheader("Highlights and Analysis")
                                    st.write(highlights_summary)

                else:
                    st.warning("No PDFs found under 'Relevant Links'.")
            else:
                st.warning("No 'Relevant Links' section found.")
        else:
            st.warning("No relevant section found on the webpage.")
    except Exception as e:
        st.error(f"An error occurred while scraping or processing PDFs: {e}")

st.title("Summarization - prsindia")

prompt = (
    "You are an HTML extractor bot. You will be provided with extracted text. "
    "Your goal is to convert the text into HTML format. Ensure that the HTML has "
    "a hierarchical relationship with section headers as <h1> tags and text as <p> tags."
)

option = st.radio("Choose an option:", ("Upload a PDF", "Input a website link"))

if option == "Upload a PDF":
    uploaded_pdf = st.file_uploader("Upload a PDF file", type=["pdf"])
    if uploaded_pdf is not None:
        uploads_folder = "uploads"
        ensure_folder_exists(uploads_folder)
        images_folder = "images"
        ensure_folder_exists(images_folder)
        file_path = os.path.join(uploads_folder, uploaded_pdf.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_pdf.read())
        image_paths, num_pages = convert_pdf_to_images(file_path, images_folder)
        if image_paths:
            all_text = ""
            for image_path in image_paths:
                extracted_text = extract_text_from_image(image_path)
                if extracted_text:
                    all_text += extracted_text  
                    
            if all_text:
                html_content = process_text_with_gpt(all_text, prompt)
                if html_content:
                    json_data = html_to_json(html_content)
                    combined_text = " ".join([entry['text'] for entry in json_data if entry['text']])
                    extractive_summary, abstractive_summary, highlights_summary = generate_summaries(combined_text, num_pages)
                    
                    st.subheader("Extractive Summary")
                    st.write(extractive_summary)
                    
                    st.subheader("Abstractive Summary")
                    st.write(abstractive_summary)

                    st.subheader("Highlights and Analysis")
                    st.write(highlights_summary)

elif option == "Input a website link":
    website_url = st.text_input("Enter the website URL:")
    if website_url:
        scrape_and_download_pdfs(website_url, prompt)
