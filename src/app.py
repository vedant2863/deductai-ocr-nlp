from flask import Flask, request, jsonify, send_file
from ocr import extract_text, check_ocr_availability
from classify import classify_expense
import os
import logging
import tempfile
from datetime import datetime
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Image as PlatypusImage, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
import io

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route("/classify", methods=["POST"])
def classify():
    """Main classification endpoint - implements the detailed step-by-step flow"""
    try:
        # Step 1: Validate request
        logger.info("Step 1: Received classification request")
        
        if 'image' not in request.files:
            logger.error("No image file in request")
            return jsonify({"error": "No image file provided"}), 400
        
        file = request.files['image']
        
        if file.filename == '':
            logger.error("Empty filename")
            return jsonify({"error": "No file selected"}), 400
        
        if not allowed_file(file.filename):
            logger.error(f"Invalid file type: {file.filename}")
            return jsonify({"error": "Invalid file type. Allowed: png, jpg, jpeg, gif, bmp, tiff"}), 400
        
        # Step 2: Save uploaded image temporarily with secure filename
        logger.info("Step 2: Saving uploaded image temporarily")
        filename = secure_filename(file.filename)
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"receipt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}")
        
        try:
            file.save(temp_path)
            logger.info(f"Image saved to: {temp_path}")
        except Exception as e:
            logger.error(f"Failed to save image: {str(e)}")
            return jsonify({"error": "Failed to save uploaded image"}), 500
        
        # Step 3: Extract text using OCR
        logger.info("Step 3: Extracting text from image using OCR")
        try:
            extracted_text = extract_text(temp_path)
            logger.info(f"OCR completed. Extracted {len(extracted_text)} characters")
            
            if not extracted_text.strip():
                logger.warning("No text extracted from image")
                return jsonify({
                    "error": "No text could be extracted from the image. Please ensure the image contains readable text."
                }), 400
                
        except Exception as e:
            logger.error(f"OCR failed: {str(e)}")
            return jsonify({"error": f"Text extraction failed: {str(e)}"}), 500
        
        # Step 4: Classify expense using NLP
        logger.info("Step 4: Classifying expense using NLP model")
        try:
            category = classify_expense(extracted_text)
            logger.info(f"Classification completed. Category: {category}")
        except Exception as e:
            logger.error(f"Classification failed: {str(e)}")
            return jsonify({"error": f"Classification failed: {str(e)}"}), 500
        
        # Step 5: Clean up temporary file
        try:
            os.remove(temp_path)
            logger.info("Temporary file cleaned up")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary file: {str(e)}")
        
        # Step 6: Return results
        logger.info("Step 6: Returning classification results")
        response_data = {
            "extracted_text": extracted_text,
            "category": category,
            "confidence": "high",  # You can enhance this with actual confidence scores
            "timestamp": datetime.now().isoformat(),
            "status": "success"
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Unexpected error in classification: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large. Maximum size is 16MB."}), 413

@app.route("/pdf-report", methods=["POST"])
def generate_pdf_report_endpoint():
    """Generate a PDF report from classification data"""
    try:
        data = request.json
        image_path = data.get('image_path')
        
        if not image_path or not os.path.exists(image_path):
            return jsonify({"error": "Image path is missing or invalid"}), 400
        
        pdf_data = generate_pdf_report(image_path, data)
        
        return send_file(
            io.BytesIO(pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name='receipt_report.pdf'
        )
    except Exception as e:
        logger.error(f"PDF generation failed: {str(e)}")
        return jsonify({"error": "Failed to generate PDF"}), 500

def generate_pdf_report(image_path, classification_data):
    """Generate a PDF report with the receipt image and classification results."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title = Paragraph("DeductAI - Receipt Classification Report", styles['Title'])
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
    
    # Receipt image
    if image_path and os.path.exists(image_path):
        try:
            img_width = 4*inch
            img_height = 3*inch
            receipt_img = PlatypusImage(image_path, width=img_width, height=img_height)
            story.append(Paragraph("<b>Receipt Image:</b>", styles['Normal']))
            story.append(Spacer(1, 0.1*inch))
            story.append(receipt_img)
            story.append(Spacer(1, 0.3*inch))
        except Exception as e:
            story.append(Paragraph(f"Could not include image in PDF: {str(e)}", styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
    else:
        story.append(Paragraph("Receipt image not available", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
    
    # Extracted text
    extracted_text = classification_data.get('extracted_text', 'No text extracted')
    # Escape special characters for HTML
    extracted_text = extracted_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text_para = Paragraph(f"<b>Extracted Text:</b><br/>{extracted_text}", styles['Normal'])
    story.append(text_para)
    
    doc.build(story)
    
    pdf_data = buffer.getvalue()
    buffer.close()
    
    return pdf_data

if __name__ == "__main__":
    # Check for EasyOCR availability on startup
    if not check_ocr_availability():
        logger.warning("EasyOCR is not available. OCR functionality will not work.")
        logger.warning("Please ensure EasyOCR is installed: pip install easyocr")

    logger.info("Starting Flask server on port 5000")
    # Use host='0.0.0.0' to make it accessible from outside the container
    app.run(host='0.0.0.0', debug=True, port=5000, use_reloader=False)  # Disable reloader to prevent subprocess issues
