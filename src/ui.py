import streamlit as st
import requests
from PIL import Image
import io
import time
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Image as PlatypusImage, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

# --- Configuration ---
# Use environment variable for backend URL, default to localhost
import os
BASE_URL = os.getenv("BACKEND_URL", "http://localhost:5000")
HEALTH_CHECK_URL = f"{BASE_URL}/health"
CLASSIFY_URL = f"{BASE_URL}/classify"

# --- Helper Functions ---
def check_backend_health():
    """Check if the Flask backend is running."""
    try:
        response = requests.get(HEALTH_CHECK_URL, timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def generate_pdf_report(image, classification_data, filename="receipt_report.pdf"):
    """Generate a PDF report with the receipt image and classification results."""
    # Create a BytesIO buffer to store PDF data
    buffer = io.BytesIO()
    
    # Create the PDF document
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title = Paragraph("DeductAI - Receipt Analysis Report", styles['Title'])
    story.append(title)
    story.append(Spacer(1, 0.2*inch))
    
    # Classification results
    category = classification_data.get('category', 'N/A')
    confidence = classification_data.get('confidence', 'N/A')
    timestamp = classification_data.get('timestamp', 'N/A')
    
    results_text = f"""
    <b>Classification Results:</b><br/>
    Category: {category}<br/>
    Confidence: {confidence}<br/>
    Timestamp: {timestamp}<br/>
    """
    
    results_para = Paragraph(results_text, styles['Normal'])
    story.append(results_para)
    story.append(Spacer(1, 0.3*inch))
    
    # Receipt image - Convert PIL image to BytesIO for ReportLab
    temp_image_path = None
    try:
        # Save image to a temporary location that persists until PDF is built
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        temp_image_path = temp_file.name
        temp_file.close()  # Close file handle but keep file
        
        # Save image to the temp file
        image.save(temp_image_path, format='PNG')
        
        # Add image to PDF (resize to fit page)
        img_width = 4*inch
        img_height = 3*inch
        receipt_img = PlatypusImage(temp_image_path, width=img_width, height=img_height)
        story.append(Paragraph("<b>Original Receipt Image:</b>", styles['Normal']))
        story.append(Spacer(1, 0.1*inch))
        story.append(receipt_img)
        story.append(Spacer(1, 0.3*inch))
        
    except Exception as e:
        story.append(Paragraph(f"Could not include image in PDF: {str(e)}", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
    
    # Extracted text
    extracted_text = classification_data.get('extracted_text', 'No text extracted')
    # Escape special characters for HTML
    extracted_text = extracted_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text_para = Paragraph(f"<b>Extracted Text (OCR Results):</b><br/>{extracted_text}", styles['Normal'])
    story.append(text_para)
    
    # Build PDF
    doc.build(story)
    
    # Clean up temp file after PDF is built
    if temp_image_path:
        try:
            os.unlink(temp_image_path)
        except:
            pass
    
    # Get PDF data
    pdf_data = buffer.getvalue()
    buffer.close()
    
    return pdf_data

def generate_receipt_clone_pdf(image, classification_data, filename="receipt_clone.pdf"):
    """Generate a PDF clone of the receipt with extracted text for verification."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import black, blue, red
    import textwrap
    
    # Create a BytesIO buffer to store PDF data
    buffer = io.BytesIO()
    
    # Create canvas
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "DeductAI - Receipt Clone with Text Extraction")
    
    # Classification info
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 80, f"Category: {classification_data.get('category', 'N/A')}")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 100, f"Confidence: {classification_data.get('confidence', 'N/A')}")
    c.drawString(50, height - 115, f"Processed: {classification_data.get('timestamp', 'N/A')}")
    
    # Save image temporarily
    temp_image_path = None
    try:
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        temp_image_path = temp_file.name
        temp_file.close()
        
        # Save image to temp file
        image.save(temp_image_path, format='PNG')
        
        # Calculate image dimensions to fit on left side
        img_width = 280  # Leave space for text on right
        img_height = 350
        img_x = 50
        img_y = height - 500
        
        # Draw image
        c.drawImage(temp_image_path, img_x, img_y, width=img_width, height=img_height, preserveAspectRatio=True)
        
        # Draw border around image
        c.setStrokeColor(black)
        c.rect(img_x, img_y, img_width, img_height)
        
        # Add extracted text on the right side
        text_x = img_x + img_width + 20
        text_y = img_y + img_height - 20
        text_width = width - text_x - 50
        
        c.setFont("Helvetica-Bold", 12)
        c.drawString(text_x, text_y, "EXTRACTED TEXT:")
        
        # Format and wrap extracted text
        extracted_text = classification_data.get('extracted_text', 'No text extracted')
        
        # Split text into lines and wrap
        lines = extracted_text.split('\n')
        wrapped_lines = []
        for line in lines:
            if len(line) > 30:  # Wrap long lines
                wrapped_lines.extend(textwrap.wrap(line, width=30))
            else:
                wrapped_lines.append(line)
        
        # Draw text lines
        c.setFont("Helvetica", 9)
        y_offset = text_y - 30
        line_height = 12
        
        for i, line in enumerate(wrapped_lines[:25]):  # Limit to 25 lines to fit on page
            if y_offset > 50:  # Don't go below page margin
                c.drawString(text_x, y_offset, line.strip())
                y_offset -= line_height
        
        if len(wrapped_lines) > 25:
            c.drawString(text_x, y_offset, "[Text truncated...]")
        
        # Add verification note
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(blue)
        c.drawString(50, 80, "This is a clone of the original receipt with extracted text for verification purposes.")
        c.drawString(50, 65, "Compare the extracted text (right) with the original image (left) to verify OCR accuracy.")
        
        # Add footer
        c.setFillColor(red)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(50, 30, "Generated by DeductAI - AI-Powered Tax Deduction Classifier")
        
    except Exception as e:
        # Error handling
        c.setFont("Helvetica", 12)
        c.drawString(50, height - 200, f"Error creating receipt clone: {str(e)}")
    
    finally:
        # Clean up temp file
        if temp_image_path:
            try:
                os.unlink(temp_image_path)
            except:
                pass
    
    # Save PDF
    c.save()
    
    # Get PDF data
    pdf_data = buffer.getvalue()
    buffer.close()
    
    return pdf_data

# --- Streamlit UI ---
st.set_page_config(page_title="DeductAI: AI Tax Classifier", layout="wide")

# --- Header ---
st.title("DeductAI: AI-Powered Tax Deduction Classifier")
st.markdown("""
Welcome to DeductAI! Upload a receipt image, and our AI will analyze it and suggest the correct IRS tax deduction category. 
This demo uses local AI models (Ollama & Tesseract) to keep your data private.
""")

# --- Backend Status Check ---
if not check_backend_health():
    st.error("**Backend Server Not Detected!**")
    st.markdown("""
    Please ensure the Flask backend server (`app.py`) is running.
    You can start it by running the following command in your terminal:
    ```bash
    python src/app.py
    ```
    """)
    st.stop()  # Stop the app if backend is not available
else:
    st.success("**Backend Server is Running!** You can now upload a receipt.")

# --- File Uploader and Main Logic ---
st.header("1. Upload Your Receipt")
uploaded_file = st.file_uploader(
    "Choose a receipt image...", 
    type=["jpg", "jpeg", "png", "gif", "bmp"],
    help="Upload an image of your receipt for classification."
)

if uploaded_file:
    col1, col2 = st.columns(2)
    
    with col1:
        st.header("2. Review Your Image")
        try:
            image = Image.open(uploaded_file)
            st.image(image, caption="Uploaded Receipt", use_container_width=True)
        except Exception as e:
            st.error(f"Failed to open image: {e}")
            st.stop()

    with col2:
        st.header("3. Classify Your Expense")
        if st.button("🤖 Classify Expense", type="primary", use_container_width=True):
            with st.spinner("AI at work... Analyzing receipt..."):
                try:
                    files = {"image": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    
                    # Step 1: Send to backend
                    st.write("**Step 1:** Sending image to backend...")
                    response = requests.post(CLASSIFY_URL, files=files, timeout=90) # Increased timeout
                    
                    # Step 2: Handle response
                    if response.ok:
                        data = response.json()
                        st.write("**Step 2:** Classification successful!")
                        
                        # --- Display Results ---
                        st.header("4. Results")

                        st.success(f"**Predicted Category:** {data.get('category', 'N/A')}")

                        # --- PDF Download Buttons ---
                        col_pdf1, col_pdf2 = st.columns(2)
                        
                        with col_pdf1:
                            st.download_button(
                                label="📄 Save Analysis Report",
                                data=generate_pdf_report(image, data),
                                file_name=f"receipt_report_{int(time.time())}.pdf",
                                mime="application/pdf",
                                help="Download detailed analysis report"
                            )
                        
                        with col_pdf2:
                            st.download_button(
                                label="🖼️ Save Receipt Clone",
                                data=generate_receipt_clone_pdf(image, data),
                                file_name=f"receipt_clone_{int(time.time())}.pdf",
                                mime="application/pdf",
                                help="Download receipt clone with extracted text for verification"
                            )

                        with st.expander("View Extracted Text"):
                            st.text_area("Raw Text from Receipt", data.get('extracted_text', 'No text found.'), height=250)
                        
                        with st.expander("Classification Details"):
                            st.json(data)

                    else:
                        try:
                            error_data = response.json()
                            st.error(f"**Classification Failed:** {error_data.get('error', 'Unknown error')}")
                        except ValueError:
                            st.error(f"**Classification Failed (Status {response.status_code}):** {response.text}")

                except requests.exceptions.Timeout:
                    st.error("Request timed out. The server is taking too long to respond.")
                except requests.exceptions.RequestException as e:
                    st.error(f"An error occurred while communicating with the backend: {e}")

# --- Instructions and Footer ---
st.markdown("--- ")

# Features info
col_a, col_b, col_c = st.columns(3)
with col_a:
    st.metric("✨ Features", "AI Classification")
with col_b:
    st.metric("📄 Export", "PDF Reports")
with col_c:
    st.metric("🔒 Privacy", "100% Local")

st.info("**How it works:** This app sends your receipt to a local Flask server. The server uses EasyOCR to extract text and a local Large Language Model (via Ollama or keyword matching) to classify it. Your data never leaves your computer. You can save classification results as PDF reports for your records.")
