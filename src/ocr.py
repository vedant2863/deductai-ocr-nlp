import easyocr
import cv2
import numpy as np
import logging
import os

logger = logging.getLogger(__name__)

# Initialize EasyOCR reader (will be loaded once when first used)
_ocr_reader = None

def get_ocr_reader():
    """Get or initialize the EasyOCR reader"""
    global _ocr_reader
    if _ocr_reader is None:
        try:
            logger.info("Initializing EasyOCR reader...")
            # Initialize EasyOCR with English language
            _ocr_reader = easyocr.Reader(['en'])
            logger.info("EasyOCR reader initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize EasyOCR reader: {e}")
            _ocr_reader = None
    return _ocr_reader

def check_ocr_availability():
    """Check if EasyOCR is properly available"""
    try:
        reader = get_ocr_reader()
        if reader is not None:
            logger.info("EasyOCR is available and ready")
            return True
        else:
            logger.error("EasyOCR failed to initialize")
            return False
    except Exception as e:
        logger.error(f"EasyOCR is not available: {e}")
        return False

def preprocess_image(image_path):
    """Preprocess image to improve OCR accuracy"""
    try:
        # Read image with OpenCV
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not read image from {image_path}")
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Apply threshold to get binary image
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Remove noise with morphological operations
        kernel = np.ones((1, 1), np.uint8)
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)
        
        return cleaned
        
    except Exception as e:
        logger.warning(f"Image preprocessing failed: {str(e)}. Using original image.")
        return cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

def extract_text(image_path):
    """Extract text from image using EasyOCR"""
    try:
        logger.info(f"Starting EasyOCR extraction for: {image_path}")
        
        # Validate file exists
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        # Get EasyOCR reader
        reader = get_ocr_reader()
        if reader is None:
            raise Exception("EasyOCR reader is not available")
        
        # Try with original image first
        try:
            logger.info("Attempting OCR with original image")
            results = reader.readtext(image_path)
            
            if results:
                # Extract text from results
                extracted_texts = []
                for (bbox, text, confidence) in results:
                    if confidence > 0.5:  # Only include text with confidence > 50%
                        extracted_texts.append(text)
                
                if extracted_texts:
                    full_text = ' '.join(extracted_texts)
                    logger.info(f"EasyOCR successful with original image. Extracted {len(full_text)} characters")
                    return clean_extracted_text(full_text)
                else:
                    logger.info("No high-confidence text found with original image, trying preprocessed image")
            else:
                logger.info("No text found with original image, trying preprocessed image")
                
        except Exception as e:
            logger.warning(f"Original image OCR failed: {str(e)}. Trying with preprocessed image.")
        
        # Fallback: Try with preprocessed image
        try:
            logger.info("Attempting OCR with preprocessed image")
            preprocessed_img = preprocess_image(image_path)
            
            # Save preprocessed image temporarily for EasyOCR
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                cv2.imwrite(temp_file.name, preprocessed_img)
                temp_path = temp_file.name
            
            try:
                results = reader.readtext(temp_path)
                
                if results:
                    extracted_texts = []
                    for (bbox, text, confidence) in results:
                        if confidence > 0.3:  # Lower threshold for preprocessed image
                            extracted_texts.append(text)
                    
                    if extracted_texts:
                        full_text = ' '.join(extracted_texts)
                        logger.info(f"EasyOCR successful with preprocessed image. Extracted {len(full_text)} characters")
                        return clean_extracted_text(full_text)
                    else:
                        logger.warning("No confident text found in preprocessed image")
                        return ""
                else:
                    logger.warning("No text could be extracted from the image")
                    return ""
                    
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_path)
                except Exception:
                    logger.warning(f"Failed to delete temporary file: {temp_path}")
                finally:
                    pass
                
        except Exception as e:
            logger.error(f"Preprocessed image OCR failed: {str(e)}")
            raise Exception(f"OCR extraction failed: {str(e)}")
            
    except Exception as e:
        logger.error(f"OCR extraction completely failed: {str(e)}")
        raise Exception(f"Failed to extract text from image: {str(e)}")

def clean_extracted_text(text):
    """Clean and normalize extracted text"""
    if not text:
        return ""
    
    # Remove excessive whitespace and newlines
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    # cleaned_text = '\n'.join(lines)
    
    # Remove very short lines that might be noise (less than 2 characters)
    lines = [line for line in lines if len(line.strip()) >= 2]
    
    return '\n'.join(lines).strip()
