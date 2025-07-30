import os
import logging
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_ollama import ChatOllama
# from langchain_community.chat_models import ChatOllama
from langchain_community.llms import LlamaCpp
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
import re
# import requests
import warnings

# Suppress LangChain deprecation warnings for cleaner output
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain")

logger = logging.getLogger(__name__)

# --- LLM Configuration ---
# Default to ChatOllama, but allow fallback to LlamaCpp if model path is set
USE_LLAMA_CPP = False
MODEL_PATH = os.getenv("MODEL_PATH", "models/llama-2-7b.gguf")

if os.path.exists(MODEL_PATH) and USE_LLAMA_CPP:
    logger.info(f"Using LlamaCpp with model: {MODEL_PATH}")
    llm = LlamaCpp(
        model_path=MODEL_PATH,
        n_ctx=3072,  # Increased context size
        temperature=0.1,  # Lower temperature for more deterministic output
        n_gpu_layers=32,  # Adjust based on your GPU setup
        verbose=False,
        callback_manager=CallbackManager([StreamingStdOutCallbackHandler()])
    )
else:
    logger.info("Using ChatOllama (default)")
    try:
        llm = ChatOllama(
            model="llama3",  # Make sure this model is pulled in Ollama
            temperature=0.2,
            callback_manager=CallbackManager([StreamingStdOutCallbackHandler()])
        )
    except Exception as e:
        logger.error(f"Failed to initialize ChatOllama: {e}")
        logger.error("Please ensure Ollama is running and the specified model is available.")
        llm = None  # Set to None to handle gracefully

# --- Prompt Engineering ---
# A more robust prompt with detailed instructions and examples
prompt_template = PromptTemplate.from_template(
    """
    **Objective:** You are an expert AI assistant specializing in US tax regulations. Your task is to accurately classify a given receipt text into one of the specified IRS-approved tax deduction categories.

    **Instructions:**
    1.  **Analyze the Text:** Carefully examine the receipt content provided below.
    2.  **Identify Key Information:** Look for vendor names, item descriptions, dates, and total amounts.
    3.  **Determine the Business Purpose:** Infer the most likely business purpose of the expense.
    4.  **Select the Best Category:** Choose the *single most appropriate* category from the list.
    5.  **Output Only the Category Name:** Your final response must be *only* the category name, exactly as it appears in the list.

    **Categories:**
    - **Business Meals:** Includes expenses for meals with clients or partners for business discussions. (e.g., restaurants, cafes)
    - **Travel:** Airfare, hotels, rental cars, taxis for business trips.
    - **Office Supplies:** Stationery, software, small equipment, postage. (e.g., Staples, Office Depot)
    - **Utilities:** Business-related electricity, internet, phone bills.
    - **Home Office:** A portion of rent/mortgage, insurance, and repairs for a dedicated home office space.
    - **Advertising:** Online ads, marketing services, promotional materials.
    - **Professional Development:** Courses, workshops, conferences, books related to your industry.
    - **Insurance:** Business liability insurance, professional indemnity insurance.
    - **Legal & Professional Services:** Fees for lawyers, accountants, consultants.
    - **Vehicle Expenses:** Gas, oil, repairs, insurance for a business vehicle.
    - **Other:** For valid business expenses that do not fit into the above categories.

    **Example:**
    Receipt Text:
    '''
    The Home Depot
    123 Main Street
    Anytown, USA
    
    Light Bulbs (4-pack)  $12.99
    Extension Cord        $24.99
    ---------------------------
    Total                 $37.98
    '''
    Tax Deduction Category: Office Supplies

    **Receipt Text to Classify:**
    '''
    {text}
    '''

    **Tax Deduction Category:**
    """
)

# --- LLM Chain ---
if llm:
    chain = LLMChain(llm=llm, prompt=prompt_template)
else:
    chain = None

# --- Classification Logic ---
def fallback_classify(text):
    """
    Fallback classification using enhanced keyword matching.
    """
    text = text.lower()
    
    # Business Meals keywords (check first for food/restaurant items)
    meal_keywords = ["restaurant", "cafe", "coffee", "starbucks", "mcdonald", "food", "lunch", "dinner", "breakfast", "pizza", "deli"]
    if any(keyword in text for keyword in meal_keywords):
        return "Business Meals"
    
    # Travel keywords
    travel_keywords = ["uber", "lyft", "taxi", "flight", "hotel", "airline", "airport", "rental car", "train", "bus"]
    if any(keyword in text for keyword in travel_keywords):
        return "Travel"
    
    # Office Supplies keywords
    office_keywords = ["office depot", "staples", "supplies", "paper", "pen", "printer", "ink", "software", "computer", "laptop"]
    if any(keyword in text for keyword in office_keywords):
        return "Office Supplies"
    
    # Utilities keywords
    utility_keywords = ["internet", "phone", "electric", "utility", "verizon", "at&t", "comcast", "spectrum", "cable"]
    if any(keyword in text for keyword in utility_keywords):
        return "Utilities"
    
    # Home Office keywords
    home_keywords = ["rent", "mortgage", "home office", "workspace"]
    if any(keyword in text for keyword in home_keywords):
        return "Home Office"
    
    # Advertising keywords
    ad_keywords = ["advertising", "marketing", "google ads", "facebook ads", "promotion"]
    if any(keyword in text for keyword in ad_keywords):
        return "Advertising"
    
    # Professional Development keywords
    dev_keywords = ["course", "conference", "book", "training", "seminar", "workshop", "certification"]
    if any(keyword in text for keyword in dev_keywords):
        return "Professional Development"
    
    # Insurance keywords
    if "insurance" in text:
        return "Insurance"
    
    # Legal & Professional Services keywords
    legal_keywords = ["legal", "accountant", "consultant", "lawyer", "attorney", "cpa"]
    if any(keyword in text for keyword in legal_keywords):
        return "Legal & Professional Services"
    
    # Vehicle Expenses keywords
    vehicle_keywords = ["gas", "vehicle", "auto", "car", "fuel", "oil change", "repair"]
    if any(keyword in text for keyword in vehicle_keywords):
        return "Vehicle Expenses"
    
    return "Other"

def classify_expense(text):
    """Classify the expense using the LLM chain and parse the result."""
    if not chain:
        logger.warning("LLM chain not initialized. Using fallback classification.")
        return fallback_classify(text)
        
    if not text or not text.strip():
        logger.warning("Input text is empty. Cannot classify.")
        return "Uncertain"

    try:
        logger.info("Running LLM chain for classification...")
        raw_result = chain.run({"text": text})
        logger.info(f"Raw classification result: {raw_result}")
        
        # Parse the result to ensure it's one of the valid categories
        cleaned_result = parse_llm_output(raw_result)
        
        logger.info(f"Parsed category: {cleaned_result}")
        return cleaned_result
        
    except Exception as e:
        logger.error(f"Error during LLM chain execution: {str(e)}")
        logger.warning("LLM chain failed. Using fallback classification.")
        return fallback_classify(text)

def parse_llm_output(raw_output):
    """Extract the most likely category from the LLM's raw output."""
    if not raw_output:
        return "Other"
    
    # List of valid categories (must match the prompt)
    valid_categories = [
        "Business Meals", "Travel", "Office Supplies", "Utilities", "Home Office",
        "Advertising", "Professional Development", "Insurance", 
        "Legal & Professional Services", "Vehicle Expenses", "Other"
    ]
    
    # Use regex to find the first matching category in the output
    for category in valid_categories:
        if re.search(r"\b" + re.escape(category) + r"\b", raw_output, re.IGNORECASE):
            return category
            
    # If no specific category is found, default to "Other"
    logger.warning(f"Could not parse a valid category from: '{raw_output}'. Defaulting to 'Other'.")
    return "Other"
