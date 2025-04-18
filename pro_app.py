import streamlit as st
import hmac
import pandas as pd
import json
import os
import requests
from io import BytesIO # Use BytesIO for pptx
import docx2txt
import PyPDF2
from docx import Document
import time
import re
from datetime import datetime
from pptx import Presentation # Import Presentation for pptx

# --- Page Configuration (MUST be the first Streamlit command) ---
st.set_page_config(
    page_title="Project Health Analysis",
    page_icon="📊",
    layout="wide",
)

# --- Authentication ---
def check_password():
    """Returns `True` if the user had a correct password."""

    # Initialize login state if not present
    # Do this *before* accessing it in the form logic below
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "password_correct" not in st.session_state:
         st.session_state["password_correct"] = False # Ensure it exists

    def login_form():
        """Form with widgets to collect user information"""
        with st.form("Credentials"):
            st.text_input("Username", key="username")
            st.text_input("Password", type="password", key="password")
            # on_click calls password_entered and updates session state
            st.form_submit_button("Log in", on_click=password_entered)

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        # Ensure secrets and passwords structure exists before accessing
        # Use .get() for safer access to session_state keys
        username = st.session_state.get("username")
        password = st.session_state.get("password")

        if not username or not password:
             st.error("Username and Password are required.")
             st.session_state["password_correct"] = False
             st.session_state["logged_in"] = False
             return # Stop processing if inputs are missing

        # Check against secrets
        if "passwords" in st.secrets and username in st.secrets["passwords"]:
            stored_password = st.secrets.passwords[username]
            # Ensure stored_password is a string or bytes for hmac.compare_digest
            if isinstance(stored_password, (str, bytes)):
                # Use submitted password from session_state
                if hmac.compare_digest(password, str(stored_password)):
                    st.session_state["password_correct"] = True
                    st.session_state["logged_in"] = True # Flag user as logged in
                    # Clear sensitive info after check
                    if "password" in st.session_state: del st.session_state["password"]
                    if "username" in st.session_state: del st.session_state["username"]
                    # No rerun needed here, Streamlit handles rerun on form submission/state change
                else:
                    st.session_state["password_correct"] = False
                    st.session_state["logged_in"] = False
            else:
                st.error(f"Password configuration error for user {username}.")
                st.session_state["password_correct"] = False
                st.session_state["logged_in"] = False
        else:
             st.session_state["password_correct"] = False
             st.session_state["logged_in"] = False

        # Display error message *after* the check if login failed
        if not st.session_state.get("password_correct", False):
             # This error message might appear briefly before rerun on success,
             # consider placing it outside this callback if that's an issue.
             # However, placing it here ensures it shows immediately on failure.
             st.error("😕 User not known or password incorrect")
             # Clear password field after failed attempt
             if "password" in st.session_state: del st.session_state["password"]


    # --- Check Login Status ---

    # If user is already logged in (from a previous run/interaction), show logout
    if st.session_state.get("logged_in", False):
        if st.sidebar.button("Log out"):
            # Clear all relevant session state on logout
            for key in list(st.session_state.keys()):
                 # Keep essential Streamlit internal keys if necessary,
                 # but clearing most app-specific state is good practice.
                 # Be cautious if clearing keys used by components before rerun.
                 if key not in ['_form_tracking_id_Credentials']: # Example internal key to keep
                      del st.session_state[key]
            # Explicitly set logged_in to False after clearing
            st.session_state["logged_in"] = False
            st.session_state["password_correct"] = False
            st.rerun() # Rerun to immediately show login form
        return True # User is logged in

    # If not logged in, show the login form
    login_form()

    # Check if a login attempt just happened and failed
    # This check needs to happen *after* the form is rendered and potentially submitted
    # Use a temporary flag or check password_correct state *after* the form logic
    # Note: The error message is now inside password_entered for immediate feedback

    # Return the current login status
    return st.session_state.get("logged_in", False)


# --- Main Application Logic (only runs if authenticated) ---
# This 'if' block now runs *after* set_page_config and *after* check_password
if check_password():

    # Custom CSS (can be here or after imports, but after set_page_config)
    st.markdown("""
    <style>
        .main {
            padding: 2rem;
        }
        /* ... rest of your CSS styles ... */
        .status-green { background-color: #d4edda; color: #155724; padding: 10px; border-radius: 5px; margin-bottom: 10px; }
        .status-amber { background-color: #fff3cd; color: #856404; padding: 10px; border-radius: 5px; margin-bottom: 10px; }
        .status-red { background-color: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px; margin-bottom: 10px; }
        .metric-box { background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .score-high { color: #155724; font-weight: bold; }
        .score-medium { color: #856404; font-weight: bold; }
        .score-low { color: #721c24; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

    # Initialize session states (if not already handled by logout/login)
    # Use .setdefault() for cleaner initialization
    st.session_state.setdefault('api_key', "")
    st.session_state.setdefault('documents_content', {})
    st.session_state.setdefault('analysis_results', None)
    st.session_state.setdefault('budget_data', None)


    # --- Helper Functions (File Processing, API Calls, Display) ---

    def extract_text_from_file(file):
        """Extract text content from various file types."""
        file_extension = file.name.split('.')[-1].lower()
        file_content = file.getvalue() # Read file content once

        try:
            if file_extension == 'txt':
                try:
                    return file_content.decode('utf-8')
                except UnicodeDecodeError:
                    return file_content.decode('latin-1') # Fallback encoding

            elif file_extension == 'docx':
                # Use BytesIO for docx2txt
                return docx2txt.process(BytesIO(file_content))

            elif file_extension == 'pdf':
                pdf_reader = PyPDF2.PdfReader(BytesIO(file_content))
                text = ""
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n" # Add newline between pages
                return text

            elif file_extension == 'pptx':
                prs = Presentation(BytesIO(file_content))
                text = ""
                for slide in prs.slides:
                    for shape in slide.shapes:
                        if hasattr(shape, "text"):
                            text += shape.text + "\n"
                return text

            elif file_extension in ['csv', 'xls', 'xlsx']:
                 # Read Excel/CSV into pandas DataFrame
                if file_extension in ['xls', 'xlsx']:
                    # Make sure openpyxl is installed for xlsx, xlrd for xls
                    df = pd.read_excel(BytesIO(file_content), engine='openpyxl' if file_extension == 'xlsx' else None)
                else: # csv
                     # Attempt to read CSV, handling potential encoding issues
                    try:
                        df = pd.read_csv(BytesIO(file_content), encoding='utf-8')
                    except UnicodeDecodeError:
                        df = pd.read_csv(BytesIO(file_content), encoding='latin-1') # Fallback
                return df.to_string()

            else:
                st.warning(f"Unsupported file type: {file_extension} for file {file.name}")
                return None
        except Exception as e:
             st.error(f"Error processing file {file.name} ({file_extension}): {e}")
             return None


    def categorise_document(file_name, file_content):
        """Categorise the document type based on content and filename."""
        # Keep British English spelling
        file_name_lower = file_name.lower()
        content_lower = file_content.lower() if file_content else "" # Handle None content

        # Simple heuristics for categorisation
        if any(term in file_name_lower for term in ['sow', 'statement', 'work', 'scope']):
            return "Statement of Work"
        elif any(term in file_name_lower for term in ['plan', 'schedule', 'timeline', 'gantt']):
            return "Project Plan"
        elif any(term in file_name_lower for term in ['status', 'report', 'update', 'progress']):
            return "Status Report"
        elif any(term in file_name_lower for term in ['risk', 'issue', 'log', 'raid']):
            return "Risk and Issue Log"
        elif any(term in file_name_lower for term in ['action', 'task', 'todo', 'minutes']):
            return "Action List / Minutes"
        elif any(term in file_name_lower for term in ['budget', 'cost', 'finance', 'financial', 'spend']):
            return "Budget Document"
        elif any(term in file_name_lower for term in ['presentation', 'deck', 'slides']):
             return "Presentation"
        else:
            # Try to determine type from content
            if ('budget' in content_lower or 'financial' in content_lower) and \
               ('$' in content_lower or '€' in content_lower or '£' in content_lower or 'cost' in content_lower):
                return "Budget Document"
            elif 'risk' in content_lower and ('issue' in content_lower or 'mitigation' in content_lower):
                return "Risk and Issue Log"
            elif ('status' in content_lower and 'report' in content_lower) or 'progress update' in content_lower :
                return "Status Report"
            elif ('action item' in content_lower or 'decision log' in content_lower) and \
                 ('assigned' in content_lower or 'due' in content_lower or 'owner' in content_lower):
                return "Action List / Minutes"
            elif 'scope' in content_lower and ('deliverable' in content_lower or 'objective' in content_lower or 'requirement' in content_lower):
                return "Statement of Work"
            elif 'timeline' in content_lower or 'milestone' in content_lower or 'gantt' in content_lower:
                 return "Project Plan"
            else:
                return "Other Document"

    def extract_budget_info(documents_content):
        """Extract budget information from documents."""
        budget_data = {
            "total_budget": None, "spent": None, "remaining": None,
            "over_under": None, "details": []
        }
        # Refined regex patterns
        budget_pattern = r'(?:budget|total cost|project cost|allocated budget|approved budget)[\s:]*(?:[$£€]\s?)?([\d,]+(?:\.\d{1,2})?)\s?(?:[$£€])?'
        spent_pattern = r'(?:spent|expenses|costs to date|actual cost|expenditure)[\s:]*(?:[$£€]\s?)?([\d,]+(?:\.\d{1,2})?)\s?(?:[$£€])?'

        budget_docs = {name: content for name, content in documents_content.items()
                       if categorise_document(name, content) == "Budget Document"}
        search_docs = budget_docs if budget_docs else documents_content

        found_budgets, found_spent = [], []
        for doc_name, content in search_docs.items():
            if not content: continue
            # Use re.IGNORECASE for case-insensitivity
            budget_matches = re.findall(budget_pattern, content, re.IGNORECASE)
            spent_matches = re.findall(spent_pattern, content, re.IGNORECASE)
            for match in budget_matches:
                try:
                    val = float(str(match).replace(',', ''))
                    found_budgets.append(val)
                    budget_data["details"].append({"document": doc_name, "type": "budget", "value_found": val})
                except (ValueError, TypeError): pass
            for match in spent_matches:
                try:
                    val = float(str(match).replace(',', ''))
                    found_spent.append(val)
                    budget_data["details"].append({"document": doc_name, "type": "spent", "value_found": val})
                except (ValueError, TypeError): pass

        if found_budgets: budget_data["total_budget"] = max(found_budgets)
        if found_spent: budget_data["spent"] = max(found_spent)

        if budget_data["total_budget"] is not None and budget_data["spent"] is not None:
            budget_data["remaining"] = budget_data["total_budget"] - budget_data["spent"]
            budget_data["over_under"] = "under" if budget_data["remaining"] >= 0 else "over"
        return budget_data

    def call_claude_api(api_key, prompt, model="claude-3-sonnet-20240229"):
        """Call the Claude API directly using requests"""
        # Keep British English spelling
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json", "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
        data = {
            "model": model, "max_tokens": 4000, "temperature": 0.1,
            "system": "You are a project management expert analysing project documentation. Provide clear, objective analysis based only on the facts presented in the documents. Use British English spelling (e.g., analyse, categorise).",
            "messages": [{"role": "user", "content": prompt}]
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=180)
            response.raise_for_status()
            response_json = response.json()
            if 'content' in response_json and response_json['content'] and 'text' in response_json['content'][0]:
                return response_json['content'][0]['text']
            elif 'error' in response_json:
                 st.error(f"API Error: {response_json['error'].get('type')} - {response_json['error'].get('message')}")
                 return None
            else:
                st.error("Unexpected API response format."); st.json(response_json)
                return None
        except requests.exceptions.RequestException as e:
            st.error(f"Error calling Claude API: {e}")
            if hasattr(e, 'response') and e.response is not None:
                 st.error(f"Response status: {e.response.status_code}\nResponse text: {e.response.text}")
            return None
        except Exception as e:
            st.error(f"An unexpected error occurred during API call: {str(e)}")
            return None

    def analyse_project_with_claude(api_key, documents_content):
        """Send project documents to Claude for analysis."""
        # Keep British English spelling
        budget_data = extract_budget_info(documents_content)
        try:
            docs_formatted, total_chars = "", 0
            char_limit = 150000
            for filename, content in documents_content.items():
                 if not content: continue
                 doc_type = categorise_document(filename, content)
                 content_to_add = f"\n\n--- DOCUMENT: {filename} (Type: {doc_type}) ---\n{content}"
                 if total_chars + len(content_to_add) > char_limit:
                     remaining_chars = char_limit - total_chars
                     if remaining_chars > 200:
                         content_to_add = content_to_add[:remaining_chars] + "... [TRUNCATED]"
                     else:
                         st.warning(f"Content limit reached, skipping document: {filename}"); continue
                 docs_formatted += content_to_add
                 total_chars += len(content_to_add)

            budget_info = "\nBudget Summary (automatically extracted):\n"
            # ... (rest of budget_info formatting as before) ...
            if budget_data.get("total_budget") is not None:
                budget_info += f"- Total Budget: £{budget_data['total_budget']:,.2f}\n" # Assuming GBP
                if budget_data.get("spent") is not None:
                    budget_info += f"- Spent: £{budget_data['spent']:,.2f}\n"
                    budget_info += f"- Remaining: £{budget_data['remaining']:,.2f}\n"
                    budget_info += f"- Status: {budget_data['over_under']}spend\n"
                else: budget_info += "- Spent: Not clearly identified\n"
            else: budget_info += "- Total Budget: Not clearly identified\n"
            budget_info += f"- Budget Details Found: {len(budget_data.get('details',[]))} potential figures identified."

            prompt = f"""
            You are a project management expert reviewing project documentation. Analyse the provided project documents looking for these key aspects:
            {/* ... rest of prompt as before, ensuring British English ... */}
            1. Scope creep indicators (unplanned changes, new requests not in original scope)
            2. Dependency mapping quality (are dependencies clearly identified and tracked?)
            3. Objective and goal setting quality (are objectives SMART - Specific, Measurable, Achievable, Relevant, Time-bound?)
            4. Budget situation (based on provided summary and document content)
            5. Planning quality (is the plan detailed, realistic, with clear milestones?)
            6. Key risks and issues (identify major threats and problems)

            Based on your analysis, provide the following outputs:
            {/* ... rest of output specification as before ... */}
            1. Scope Creep: List specific instances or indicators of potential scope creep (as bullet points). If none, state "No specific scope creep indicators identified".
            2. Dependency Mapping: Score the quality from 1-10 (1=poor, 10=excellent) and briefly explain your reasoning.
            3. Objective Setting: Score the quality from 1-10 and provide specific examples of good/poor objectives found in the documents.
            4. Budget Analysis: Briefly analyse the budget situation based on the summary provided ({budget_info}) and any further details in the documents. Mention any discrepancies or concerns.
            5. Planning Quality: Score the quality from 1-10 and explain your reasoning.
            6. Risks & Issues: Identify the top 3-5 most significant risks and issues mentioned.
            7. Project Status: Based *only* on the information in the documents, classify the project's overall health as: GREEN, AMBER, or RED. Provide a concise justification (1-2 sentences) for this status, referencing specific evidence.

            Format your response *strictly* as a JSON object with these keys:
            "scope_creep_items": [], "dependency_mapping_score": number, "dependency_mapping_reasoning": "string",
            "objective_setting_score": number, "objective_setting_reasoning": "string",
            "objective_examples": {{"good": [], "poor": []}}, "budget_analysis": "string",
            "planning_quality_score": number, "planning_quality_reasoning": "string",
            "top_risks_issues": [], "project_status": "GREEN" | "AMBER" | "RED", "status_justification": "string"

            Ensure the entire output is a single, valid JSON object. Use British English spellings.

            Documents to analyse:
            {docs_formatted}
            """

            model = st.secrets.get("ANTHROPIC_MODEL", "claude-3-sonnet-20240229") # Safer way to get secret

            response_text = call_claude_api(api_key, prompt, model)
            if response_text:
                # Improved JSON parsing logic
                json_str = None
                if response_text.strip().startswith("```json"):
                     json_str = response_text.strip()[7:-3].strip()
                elif response_text.strip().startswith("{") and response_text.strip().endswith("}"):
                    json_str = response_text.strip()
                else:
                    json_start = response_text.find('{')
                    json_end = response_text.rfind('}') + 1
                    if json_start != -1 and json_end > json_start:
                         json_str = response_text[json_start:json_end]

                if json_str:
                    try:
                        analysis_results = json.loads(json_str)
                        expected_keys = ["scope_creep_items", "dependency_mapping_score", "objective_setting_score", "budget_analysis", "planning_quality_score", "top_risks_issues", "project_status", "status_justification"]
                        if all(key in analysis_results for key in expected_keys):
                             return analysis_results, budget_data
                        else:
                             st.error("Parsed JSON is missing expected keys."); st.json(analysis_results)
                             return None, budget_data
                    except json.JSONDecodeError as e:
                        st.error(f"Failed to parse Claude's JSON response: {e}"); st.text_area("Problematic JSON String:", json_str, height=150)
                        return None, budget_data
                else:
                    st.error("Claude did not return a recognisable JSON response."); st.text_area("Raw API Response:", response_text, height=150)
                    return None, budget_data
            else:
                return None, budget_data # Error already shown in call_claude_api
        except Exception as e:
            st.error(f"Error in project analysis process: {str(e)}")
            import traceback; st.error(traceback.format_exc())
            return None, budget_data

    def display_results(analysis_results, budget_data):
        """Display the analysis results in a formatted Streamlit interface."""
        # Keep British English spelling
        if not analysis_results:
            st.error("No analysis results to display.")
            return

        status = analysis_results.get("project_status", "UNKNOWN").upper()
        status_justification = analysis_results.get('status_justification', 'N/A')
        # Display status header (using f-strings and conditional logic)
        status_color_class = f"status-{status.lower()}" if status in ["GREEN", "AMBER", "RED"] else ""
        status_icon = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}.get(status, "❓")
        st.markdown(f"""<div class="{status_color_class}">
                      <h2>Project Status: {status_icon} {status}</h2>
                      <p>{status_justification}</p>
                    </div>""", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Quality Scores (out of 10)")
            # Use a helper function for metric boxes to reduce repetition
            def metric_box(title, score_key, reason_key):
                 score = analysis_results.get(score_key, "N/A")
                 reason = analysis_results.get(reason_key, "N/A")
                 st.markdown(f"""<div class="metric-box">
                               <h4>{title}</h4>
                               <p class="{get_score_class(score)}">Score: {score}/10</p>
                               <p><i>Reasoning:</i> {reason}</p>
                             </div>""", unsafe_allow_html=True)

            metric_box("Dependency Mapping", "dependency_mapping_score", "dependency_mapping_reasoning")
            metric_box("Objective Setting (SMART)", "objective_setting_score", "objective_setting_reasoning")
            metric_box("Planning Quality", "planning_quality_score", "planning_quality_reasoning")

            st.subheader("Objective Examples")
            obj_examples = analysis_results.get('objective_examples', {})
            with st.expander("View Objective Examples"):
                 st.markdown("##### Good Examples:")
                 good_obj = obj_examples.get('good', [])
                 st.markdown('\n'.join(f"- {ex}" for ex in good_obj) if good_obj else "_No specific good examples identified._")
                 st.markdown("##### Poor Examples:")
                 poor_obj = obj_examples.get('poor', [])
                 st.markdown('\n'.join(f"- {ex}" for ex in poor_obj) if poor_obj else "_No specific poor examples identified._")

        with col2:
            st.subheader("Scope Creep Indicators")
            scope_items = analysis_results.get("scope_creep_items", [])
            st.markdown('<div class="metric-box">', unsafe_allow_html=True)
            if scope_items and scope_items[0] != "No specific scope creep indicators identified":
                st.markdown('\n'.join(f"- {item}" for item in scope_items))
            else:
                st.markdown("<p><i>No specific scope creep indicators identified.</i></p>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            st.subheader("Top Risks & Issues")
            risk_items = analysis_results.get("top_risks_issues", [])
            st.markdown('<div class="metric-box">', unsafe_allow_html=True)
            if risk_items:
                st.markdown('\n'.join(f"{i}. {item}" for i, item in enumerate(risk_items, 1)))
            else:
                 st.markdown("<p><i>No specific risks or issues highlighted.</i></p>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            st.subheader("Budget Analysis")
            st.markdown('<div class="metric-box">', unsafe_allow_html=True)
            st.markdown(f"<p>{analysis_results.get('budget_analysis', 'N/A')}</p>", unsafe_allow_html=True)
            if budget_data and budget_data.get("total_budget") is not None:
                st.markdown("--- ##### Extracted Budget Summary:")
                st.markdown(f"<p>Total Budget: <strong>£{budget_data['total_budget']:,.2f}</strong></p>", unsafe_allow_html=True)
                if budget_data.get("spent") is not None:
                    over_under_class = "score-high" if budget_data["over_under"] == "under" else "score-low"
                    st.markdown(f"""
                        <p>Spent to Date: <strong>£{budget_data['spent']:,.2f}</strong></p>
                        <p>Remaining: <strong>£{budget_data['remaining']:,.2f}</strong></p>
                        <p class="{over_under_class}">Status: {budget_data['over_under'].upper()}SPEND</p>
                    """, unsafe_allow_html=True)
                else: st.markdown("<p>Spent to Date: <i>Not clearly identified</i></p>", unsafe_allow_html=True)
            elif budget_data and budget_data.get("details"):
                 st.markdown("--- ##### Extracted Budget Summary:")
                 st.markdown("<p><i>Total budget/spent not definitively determined. Potential figures found.</i></p>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    def get_score_class(score):
        """Return CSS class based on score value."""
        try:
            score_num = float(score)
            if score_num >= 7: return "score-high"
            elif score_num >= 4: return "score-medium"
            else: return "score-low"
        except (ValueError, TypeError): return "" # No class if not a number


    # --- UI Rendering ---

    st.title("Project Health Analysis")
    st.markdown("Upload project documents to analyse key project management indicators using AI.")

    # Sidebar configuration
    with st.sidebar:
        st.header("Configuration")
        api_key_source = "secrets"
        try: # Check for API key in secrets
            if "ANTHROPIC_API_KEY" in st.secrets and st.secrets["ANTHROPIC_API_KEY"]:
                st.session_state.api_key = st.secrets["ANTHROPIC_API_KEY"]
                st.success("✅ Anthropic API key loaded.")
            else: raise KeyError # Force fallback to input if key is empty or not present
        except Exception:
            api_key_source = "input"
            st.session_state.api_key = st.text_input(
                "Anthropic API Key", value=st.session_state.get('api_key',""),
                type="password", help="Required for analysis. Store as secret 'ANTHROPIC_API_KEY' for security."
            )
            if not st.session_state.api_key:
                 st.warning("API Key is required.")

        # ... (rest of sidebar content: Supported Types, About) ...
        st.markdown("---")
        st.markdown("### Supported Document Types")
        st.markdown("- Text (`.txt`)\n- PDF (`.pdf`)\n- Word (`.docx`)\n- PowerPoint (`.pptx`)\n- Excel (`.xlsx`, `.xls`)\n- CSV (`.csv`)")
        st.markdown("---")
        st.markdown("### About")
        st.markdown("This app uses Claude AI to analyse project documents for insights on scope, dependencies, objectives, budget, planning, and risks/issues. An overall RAG status is provided.")


    # --- Main Page Content ---
    st.header("1. Document Upload")
    uploaded_files = st.file_uploader(
        "Upload Project Documents", accept_multiple_files=True,
        type=["txt", "pdf", "docx", "csv", "xlsx", "xls", "pptx"],
        help="Upload relevant project files."
    )

    # File Processing and Display Area
    if uploaded_files:
        # Check if files have changed since last run to avoid reprocessing
        # Create a tuple of file names and sizes as a simple change indicator
        current_file_set = tuple((f.name, f.size) for f in uploaded_files)
        if current_file_set != st.session_state.get("_last_uploaded_files", None):
            st.session_state.documents_content = {} # Clear previous content
            st.markdown("--- #### Processing Uploaded Files...")
            progress_bar = st.progress(0)
            status_text = st.empty()
            docs_processed = {}
            processing_errors = False

            for i, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"Processing {uploaded_file.name}...")
                content = extract_text_from_file(uploaded_file)
                if content is not None:
                    doc_type = categorise_document(uploaded_file.name, content)
                    st.session_state.documents_content[uploaded_file.name] = content
                    docs_processed[uploaded_file.name] = doc_type
                    status_text.text(f"Processed {uploaded_file.name} (Detected as: {doc_type})")
                else:
                    processing_errors = True # Error already shown
                progress_bar.progress((i + 1) / len(uploaded_files))

            status_text.text("File processing complete.")
            st.session_state["_last_uploaded_files"] = current_file_set # Store indicator of processed files

            # Display summary only after processing loop finishes
            st.markdown("#### Successfully Processed Documents:")
            if docs_processed:
                 df_processed = pd.DataFrame(docs_processed.items(), columns=['Filename', 'Detected Type'])
                 st.dataframe(df_processed, use_container_width=True)
            else: st.info("No documents were successfully processed.")
            if processing_errors: st.warning("Some files could not be processed.")
        else:
             # Files haven't changed, maybe just show the summary again quickly
             st.markdown("#### Previously Processed Documents:")
             if st.session_state.documents_content:
                  processed_types = {name: categorise_document(name, content) for name, content in st.session_state.documents_content.items()}
                  df_processed = pd.DataFrame(processed_types.items(), columns=['Filename', 'Detected Type'])
                  st.dataframe(df_processed, use_container_width=True)
             else: st.info("No documents currently processed.")


    # Analysis Trigger Section
    st.markdown("---")
    st.header("2. Run Analysis")
    if st.session_state.documents_content:
        col_run, col_clear = st.columns(2)
        with col_run:
             disable_analysis = not st.session_state.api_key
             if disable_analysis: st.warning("Anthropic API Key required in sidebar.")
             analyze_button = st.button("Analyse Project Health", disabled=disable_analysis, type="primary")
        with col_clear:
            if st.button("Clear Uploaded Files & Results"):
                st.session_state.documents_content = {}
                st.session_state.analysis_results = None
                st.session_state.budget_data = None
                st.session_state["_last_uploaded_files"] = None # Clear file tracking
                st.success("Cleared documents and results.")
                time.sleep(1); st.rerun()

        if analyze_button and not disable_analysis:
            with st.spinner("Analysing project documentation with AI..."):
                analysis_results, budget_data = analyse_project_with_claude(
                    st.session_state.api_key, st.session_state.documents_content
                )
                if analysis_results:
                    st.session_state.analysis_results = analysis_results
                    st.session_state.budget_data = budget_data
                    st.success("Analysis complete!")
                    st.rerun() # Rerun to display results
                else:
                    st.error("Analysis failed. Check errors above.")
                    # Keep old results if new analysis fails? Optional.
                    # st.session_state.analysis_results = None
                    # st.session_state.budget_data = None

    elif uploaded_files: st.warning("No documents successfully processed for analysis.")
    else: st.info("👆 Upload project documents to begin.")


    # Display Results Section
    if st.session_state.analysis_results:
        st.markdown("---")
        st.header("3. Project Health Report")
        display_results(st.session_state.analysis_results, st.session_state.budget_data)

        col_clear_report, col_download = st.columns(2)
        with col_clear_report:
             if st.button("Clear Analysis Report", help="Clears only the displayed report."):
                    st.session_state.analysis_results = None
                    st.session_state.budget_data = None
                    st.success("Analysis report cleared."); time.sleep(1); st.rerun()

        with col_download:
             # Add download button for report
             try:
                 timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                 # Simplified report generation for brevity (use previous detailed logic)
                 report_md = f"# Project Health Analysis Report - {timestamp}\n\n"
                 report_md += f"## Status: {st.session_state.analysis_results.get('project_status', 'N/A')}\n"
                 report_md += f"Justification: {st.session_state.analysis_results.get('status_justification', 'N/A')}\n\n"
                 # ... (add other sections as needed from previous logic) ...
                 report_md += "## Scores\n"
                 report_md += f"- Dependency Mapping: {st.session_state.analysis_results.get('dependency_mapping_score', 'N/A')}/10\n"
                 report_md += f"- Objective Setting: {st.session_state.analysis_results.get('objective_setting_score', 'N/A')}/10\n"
                 report_md += f"- Planning Quality: {st.session_state.analysis_results.get('planning_quality_score', 'N/A')}/10\n\n"
                 # ... (add Scope, Risks, Budget etc.) ...

                 st.download_button(
                    label="Download Report (Markdown)", data=report_md.encode('utf-8'),
                    file_name=f"project_health_report_{timestamp}.md", mime="text/markdown"
                 )
             except Exception as e:
                 st.error(f"Error generating download report: {e}")

# --- End of main logic block guarded by check_password() ---
