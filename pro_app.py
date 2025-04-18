import streamlit as st
import hmac
import pandas as pd
import json
import os
import requests
from io import StringIO
import docx2txt
import PyPDF2
from docx import Document
import time
import re
from datetime import datetime
import pptx

def check_password():
    """Returns `True` if the user had a correct password."""

    def login_form():
        """Form with widgets to collect user information"""
        with st.form("Credentials"):
            st.text_input("Username", key="username")
            st.text_input("Password", type="password", key="password")
            st.form_submit_button("Log in", on_click=password_entered)

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        # Ensure secrets and passwords structure exists before accessing
        if "passwords" in st.secrets and st.session_state["username"] in st.secrets["passwords"]:
            stored_password = st.secrets.passwords[st.session_state["username"]]
            # Ensure stored_password is a string or bytes for hmac.compare_digest
            if isinstance(stored_password, (str, bytes)):
                 if hmac.compare_digest(
                    st.session_state["password"],
                    str(stored_password) # Ensure it's compared as string if needed
                 ):
                    st.session_state["password_correct"] = True
                    del st.session_state["password"]  # Don't store the username or password.
                    del st.session_state["username"]
                    return # Exit function on success
            else:
                 st.error(f"Password configuration error for user {st.session_state['username']}.")

        # If checks failed or structure doesn't exist
        st.session_state["password_correct"] = False


    # Return True if the username + password is validated.
    if st.session_state.get("password_correct", False):
        return True

    # Show inputs for username + password.
    login_form()
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("😕 User not known or password incorrect")
    return False

def logout():
    """Clear the session state and log out the user."""
    # Reset the password_correct flag to False
    st.session_state["password_correct"] = False
    # Rerun the app to show the login form
    st.experimental_rerun()

def clear_analysis():
    """Clear the analysis results and uploaded documents."""
    if 'documents_content' in st.session_state:
        st.session_state.documents_content = {}
    if 'analysis_results' in st.session_state:
        st.session_state.analysis_results = None
    if 'budget_data' in st.session_state:
        st.session_state.budget_data = None
    st.experimental_rerun()

if not check_password():
    st.stop()

# Set page configuration
st.set_page_config(
    page_title="Project Health Analysis",
    page_icon="📊",
    layout="wide",
)

# Custom CSS
st.markdown("""
<style>
    .main {
        padding: 2rem;
    }
    .status-green {
        background-colour: #d4edda;
        colour: #155724;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    .status-amber {
        background-colour: #fff3cd;
        colour: #856404;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    .status-red {
        background-colour: #f8d7da;
        colour: #721c24;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    .metric-box {
        background-colour: #f8f9fa;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 15px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    .score-high {
        colour: #155724;
        font-weight: bold;
    }
    .score-medium {
        colour: #856404;
        font-weight: bold;
    }
    .score-low {
        colour: #721c24;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session states
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""
if 'documents_content' not in st.session_state:
    st.session_state.documents_content = {}
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None
if 'budget_data' not in st.session_state:
    st.session_state.budget_data = None

def extract_text_from_pptx(file):
    """Extract text from PowerPoint files."""
    prs = pptx.Presentation(file)
    text = ""
    
    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text += shape.text + "\n"
    
    return text

def extract_text_from_file(file):
    """Extract text content from various file types."""
    file_extension = file.name.split('.')[-1].lower()
    
    if file_extension == 'txt':
        return file.getvalue().decode('utf-8')
    
    elif file_extension == 'docx':
        text = docx2txt.process(file)
        return text
    
    elif file_extension == 'pdf':
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page_num in range(len(pdf_reader.pages)):
            text += pdf_reader.pages[page_num].extract_text()
        return text
    
    elif file_extension in ['csv', 'xls', 'xlsx']:
        df = pd.read_excel(file) if file_extension in ['xls', 'xlsx'] else pd.read_csv(file)
        return df.to_string()
    
    elif file_extension in ['ppt', 'pptx']:
        return extract_text_from_pptx(file)
    
    else:
        st.error(f"Unsupported file type: {file_extension}")
        return None

def categorise_document(file_name, file_content):
    """Categorise the document type based on content and filename."""
    file_name_lower = file_name.lower()
    
    # Simple heuristics for categorisation
    if any(term in file_name_lower for term in ['sow', 'statement', 'work']):
        return "Statement of Work"
    elif any(term in file_name_lower for term in ['plan', 'schedule', 'timeline']):
        return "Project Plan"
    elif any(term in file_name_lower for term in ['status', 'report', 'update']):
        return "Status Report"
    elif any(term in file_name_lower for term in ['risk', 'issue', 'log']):
        return "Risk and Issue Log"
    elif any(term in file_name_lower for term in ['action', 'task', 'todo']):
        return "Action List"
    elif any(term in file_name_lower for term in ['budget', 'cost', 'finance']):
        return "Budget Document"
    elif any(term in file_name_lower for term in ['ppt', 'presentation', 'slide']):
        return "Presentation"
    else:
        # Try to determine type from content
        content_lower = file_content.lower()
        if 'budget' in content_lower and ('$' in content_lower or '€' in content_lower or '£' in content_lower):
            return "Budget Document"
        elif 'risk' in content_lower and 'issue' in content_lower:
            return "Risk and Issue Log"
        elif 'status' in content_lower and 'report' in content_lower:
            return "Status Report"
        elif 'action' in content_lower and ('assigned' in content_lower or 'due' in content_lower):
            return "Action List"
        elif 'scope' in content_lower and 'deliverable' in content_lower:
            return "Statement of Work"
        else:
            return "Other Document"

def extract_budget_info(documents_content):
    """Extract budget information from documents."""
    budget_data = {
        "total_budget": None,
        "spent": None, 
        "remaining": None,
        "over_under": None,
        "details": []
    }
    
    budget_pattern = r'(?:budget|total cost|project cost|allocated budget|approved budget)[\s:]*[$£€]?\s*([\d,]+(?:\.\d{2})?)'
    spent_pattern = r'(?:spent|expenses|costs to date|actual cost)[\s:]*[$£€]?\s*([\d,]+(?:\.\d{2})?)'
    
    # First pass to find budget documents
    budget_docs = {name: content for name, content in documents_content.items() 
                  if categorise_document(name, content) == "Budget Document"}
    
    # If no explicit budget documents, search all documents
    if not budget_docs:
        budget_docs = documents_content
    
    for doc_name, content in budget_docs.items():
        # Look for budget figures
        budget_matches = re.findall(budget_pattern, content.lower())
        spent_matches = re.findall(spent_pattern, content.lower())
        
        if budget_matches:
            try:
                budget_value = float(budget_matches[0].replace(',', ''))
                if budget_data["total_budget"] is None or budget_value > budget_data["total_budget"]:
                    budget_data["total_budget"] = budget_value
                budget_data["details"].append({
                    "document": doc_name,
                    "budget_found": budget_value
                })
            except ValueError:
                pass
                
        if spent_matches:
            try:
                spent_value = float(spent_matches[0].replace(',', ''))
                if budget_data["spent"] is None or spent_value > budget_data["spent"]:
                    budget_data["spent"] = spent_value
                budget_data["details"].append({
                    "document": doc_name,
                    "spent_found": spent_value
                })
            except ValueError:
                pass
    
    # Calculate remaining and over/under
    if budget_data["total_budget"] is not None and budget_data["spent"] is not None:
        budget_data["remaining"] = budget_data["total_budget"] - budget_data["spent"]
        budget_data["over_under"] = "under" if budget_data["remaining"] > 0 else "over"
    
    return budget_data

def call_claude_api(api_key, prompt, model="claude-3-sonnet-20240229"):
    """Call the Claude API directly using requests"""
    url = "https://api.anthropic.com/v1/messages"
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01"
    }
    
    data = {
        "model": model,
        "max_tokens": 4000,
        "temperature": 0,
        "system": "You are a project management expert analysing project documentation. Provide clear, objective analysis based only on the facts presented.",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 200:
            st.error(f"API Error: {response.status_code}")
            st.error(response.text)
            return None
            
        response_json = response.json()
        if 'content' in response_json and len(response_json['content']) > 0:
            return response_json['content'][0]['text']
        else:
            st.error("Empty response from API")
            return None
    except Exception as e:
        st.error(f"Error calling Claude API: {str(e)}")
        return None

def analyse_project_with_claude(api_key, documents_content):
    """Send project documents to Claude for analysis."""
    # Define budget_data initially to avoid UnboundLocalError
    budget_data = extract_budget_info(documents_content)
    
    try:
        # Prepare documents for Claude
        docs_formatted = ""
        for filename, content in documents_content.items():
            doc_type = categorise_document(filename, content)
            docs_formatted += f"\n\n--- DOCUMENT: {filename} (Type: {doc_type}) ---\n{content[:10000]}"  # Limiting content length
        
        budget_info = ""
        if budget_data["total_budget"] is not None:
            budget_info = f"\nTotal Budget: ${budget_data['total_budget']:,.2f}"
            if budget_data["spent"] is not None:
                budget_info += f"\nSpent: ${budget_data['spent']:,.2f}"
                budget_info += f"\nRemaining: ${budget_data['remaining']:,.2f}"
                budget_info += f"\nStatus: {budget_data['over_under']}spend"
        
        # Prompt for Claude
        prompt = f"""
        You are a project management expert reviewing project documentation. Analyse the provided project documents looking for these key aspects:
        
        1. Scope creep indicators
        2. Dependency mapping quality
        3. Objective and goal setting quality
        4. Budget restrictions and constraints
        5. Planning quality
        6. Key risks and issues
        
        Based on your analysis, provide the following outputs:
        
        1. Scope Creep: List specific instances of potential scope creep you identified (as bullet points)
        2. Dependency Mapping: Score the quality from 1-10 and explain your reasoning
        3. Objective Setting: Score the quality from 1-10 and provide examples of good/poor objectives
        4. Budget Analysis: Analyse the budget information: {budget_info}
        5. Planning Quality: Score the quality from 1-10 and explain your reasoning
        6. Risks & Issues: Identify the top 5 risks and issues
        7. Project Status: Based on your analysis, determine if the project should be classified as:
           - GREEN (on track)
           - AMBER (at risk)
           - RED (critical issues)
           Provide a brief justification for this status.
        
        Format your response as a JSON object with these keys: 
        scope_creep_items (array), 
        dependency_mapping_score (number), 
        dependency_mapping_reasoning (string), 
        objective_setting_score (number), 
        objective_setting_reasoning (string), 
        objective_examples (object with good and poor keys), 
        budget_analysis (string), 
        planning_quality_score (number), 
        planning_quality_reasoning (string), 
        top_risks_issues (array), 
        project_status (string), 
        status_justification (string)
        
        Documents to analyse:
        {docs_formatted}
        """
        
        # Get model from secrets if available
        model = "claude-3-sonnet-20240229"
        try:
            if "ANTHROPIC_MODEL" in st.secrets:
                model = st.secrets["ANTHROPIC_MODEL"]
        except:
            pass
            
        # Make a direct API call to Claude
        response_text = call_claude_api(api_key, prompt, model)
        
        if response_text:
            # Look for JSON object in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                try:
                    analysis_results = json.loads(json_str)
                    return analysis_results, budget_data
                except json.JSONDecodeError:
                    st.error("Failed to parse Claude's JSON response")
                    st.text(json_str)
                    return None, budget_data
            else:
                st.error("Claude did not return a proper JSON response")
                st.text(response_text)
                return None, budget_data
        else:
            st.error("Failed to get a valid response from Claude API")
            return None, budget_data
            
    except Exception as e:
        st.error(f"Error in project analysis process: {str(e)}")
        return None, budget_data

def display_results(analysis_results, budget_data):
    """Display the analysis results in a formatted Streamlit interface."""
    if not analysis_results:
        st.error("No analysis results to display.")
        return
    
    # Project Status Header with appropriate styling
    status = analysis_results.get("project_status", "").upper()
    if status == "GREEN":
        st.markdown(f"""<div class="status-green">
                      <h2>Project Status: 🟢 GREEN</h2>
                      <p>{analysis_results.get('status_justification', '')}</p>
                    </div>""", unsafe_allow_html=True)
    elif status == "AMBER":
        st.markdown(f"""<div class="status-amber">
                      <h2>Project Status: 🟡 AMBER</h2>
                      <p>{analysis_results.get('status_justification', '')}</p>
                    </div>""", unsafe_allow_html=True)
    elif status == "RED":
        st.markdown(f"""<div class="status-red">
                      <h2>Project Status: 🔴 RED</h2>
                      <p>{analysis_results.get('status_justification', '')}</p>
                    </div>""", unsafe_allow_html=True)
    
    # Create two columns for layout
    col1, col2 = st.columns(2)
    
    # Column 1: Scores and Budget
    with col1:
        # Dependency Mapping Score
        dep_score = analysis_results.get("dependency_mapping_score", 0)
        st.markdown(f"""<div class="metric-box">
                      <h3>Dependency Mapping Quality</h3>
                      <p class="{get_score_class(dep_score)}">Score: {dep_score}/10</p>
                      <p>{analysis_results.get('dependency_mapping_reasoning', '')}</p>
                    </div>""", unsafe_allow_html=True)
        
        # Objective Setting Score
        obj_score = analysis_results.get("objective_setting_score", 0)
        
        # Create the metric box with score and reasoning
        st.markdown(f"""<div class="metric-box">
                      <h3>Objective Setting Quality</h3>
                      <p class="{get_score_class(obj_score)}">Score: {obj_score}/10</p>
                      <p>{analysis_results.get('objective_setting_reasoning', '')}</p>
                    </div>""", unsafe_allow_html=True)
        
        # Handle good objectives list with proper formatting
        st.subheader("Good Objectives:")
        good_objectives = analysis_results.get('objective_examples', {}).get('good', [])
        if good_objectives:
            for example in good_objectives:
                st.markdown(f"- {example}")
        else:
            st.markdown("No good objectives identified.")
            
        # Handle poor objectives list with proper formatting
        st.subheader("Poor Objectives:")
        poor_objectives = analysis_results.get('objective_examples', {}).get('poor', [])
        if poor_objectives:
            for example in poor_objectives:
                st.markdown(f"- {example}")
        else:
            st.markdown("No poor objectives identified.")
        
        # Planning Quality Score
        plan_score = analysis_results.get("planning_quality_score", 0)
        st.markdown(f"""<div class="metric-box">
                      <h3>Planning Quality</h3>
                      <p class="{get_score_class(plan_score)}">Score: {plan_score}/10</p>
                      <p>{analysis_results.get('planning_quality_reasoning', '')}</p>
                    </div>""", unsafe_allow_html=True)
    
    # Column 2: Scope Creep, Risks, Budget
    with col2:
        # Scope Creep Items
        st.markdown("""<div class="metric-box">
                      <h3>Scope Creep Items</h3>
                    </div>""", unsafe_allow_html=True)
        
        scope_creep_items = analysis_results.get("scope_creep_items", [])
        if scope_creep_items:
            for item in scope_creep_items:
                st.markdown(f"- {item}")
        else:
            st.markdown("No scope creep items identified.")
        
        # Top Risks and Issues
        st.markdown("""<div class="metric-box">
                      <h3>Top Risks and Issues</h3>
                    </div>""", unsafe_allow_html=True)
        
        top_risks = analysis_results.get("top_risks_issues", [])
        if top_risks:
            for i, item in enumerate(top_risks, 1):
                st.markdown(f"{i}. {item}")
        
        # Budget Analysis
        st.markdown("""<div class="metric-box">
                      <h3>Budget Analysis</h3>""", unsafe_allow_html=True)
        
        if budget_data and budget_data["total_budget"] is not None:
            st.markdown(f"""
                <p>Total Budget: <strong>${budget_data['total_budget']:,.2f}</strong></p>
            """, unsafe_allow_html=True)
            
            if budget_data["spent"] is not None:
                over_under_class = "score-high" if budget_data["over_under"] == "under" else "score-low"
                st.markdown(f"""
                    <p>Spent to Date: <strong>${budget_data['spent']:,.2f}</strong></p>
                    <p>Remaining: <strong>${budget_data['remaining']:,.2f}</strong></p>
                    <p class="{over_under_class}">Status: {budget_data['over_under'].upper()}SPEND</p>
                """, unsafe_allow_html=True)
        else:
            st.markdown(f"<p>{analysis_results.get('budget_analysis', 'No budget information available')}</p>", unsafe_allow_html=True)
            
        st.markdown("</div>", unsafe_allow_html=True)

def get_score_class(score):
    """Return CSS class based on score value."""
    if score >= 7:
        return "score-high"
    elif score >= 4:
        return "score-medium"
    else:
        return "score-low"

# Main App UI
st.title("Project Health Analysis")
st.markdown("Upload project documents to analyse key project management indicators")

# Add logout button in the top right
col1, col2, col3 = st.columns([1, 1, 1])
with col3:
    if st.button("Logout", key="logout_button", help="Click to log out"):
        logout()

# Sidebar configuration - Handle API key from secrets or input
with st.sidebar:
    st.header("Configuration")
    
    # Try to get API key from secrets
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            api_key = st.secrets["ANTHROPIC_API_KEY"]
            st.success("✅ API key loaded from secrets")
        else:
            api_key = st.text_input("Anthropic API Key", value=st.session_state.api_key, type="password")
    except:
        api_key = st.text_input("Anthropic API Key", value=st.session_state.api_key, type="password")
    
    if api_key != st.session_state.api_key:
        st.session_state.api_key = api_key
    
    st.markdown("---")
    st.markdown("### Document Types")
    st.markdown("""
    - Statement of Work
    - Project Plans
    - Status Reports
    - Risk & Issue Logs
    - Action Lists
    - Budget Documents
    - Presentations
    """)
    
    st.markdown("---")
    st.markdown("### About")
    st.markdown("""
    This app uses Claude AI to analyse project documents and provide insights on:
    - Scope creep
    - Dependency mapping
    - Objective quality
    - Budget constraints
    - Planning quality
    - Key risks and issues
    
    The app will provide an overall project health status (RED/AMBER/GREEN) based on the analysis.
    """)

# Upload Section
st.header("Document Upload")
uploaded_files = st.file_uploader("Upload Project Documents", accept_multiple_files=True, 
                                 type=["txt", "pdf", "docx", "csv", "xlsx", "xls", "ppt", "pptx"])

# Add a Clear Analysis button
clear_col1, clear_col2 = st.columns([3, 1])
with clear_col2:
    if st.button("Clear Analysis", help="Clear all uploaded documents and analysis results"):
        clear_analysis()

if uploaded_files:
    docs_container = st.container()
    with docs_container:
        st.markdown("### Uploaded Documents")
        for uploaded_file in uploaded_files:
            content = extract_text_from_file(uploaded_file)
            if content:
                doc_type = categorise_document(uploaded_file.name, content)
                st.session_state.documents_content[uploaded_file.name] = content
                st.write(f"✅ {uploaded_file.name} - Detected as: {doc_type}")
            else:
                st.write(f"❌ Failed to process {uploaded_file.name}")
    
    if len(st.session_state.documents_content) > 0:
        st.markdown("---")
        analyse_button = st.button("Run Project Health Analysis")
        
        if analyse_button:
            if not st.session_state.api_key:
                st.error("Please enter your Anthropic API Key in the sidebar")
            else:
                with st.spinner("Analysing project documentation... This may take a minute."):
                    analysis_results, budget_data = analyse_project_with_claude(
                        st.session_state.api_key, 
                        st.session_state.documents_content
                    )
                    
                    if analysis_results:
                        st.session_state.analysis_results = analysis_results
                        st.session_state.budget_data = budget_data
                        st.success("Analysis complete!")
                        st.experimental_rerun()

# Display Results Section
if st.session_state.analysis_results:
    st.markdown("---")
    st.header("Project Health Report")
    display_results(st.session_state.analysis_results, st.session_state.budget_data)
    
    # Add download button for report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create a formatted report for download - using a safer string building approach
    report_md = "# Project Health Analysis Report\n"
    report_md += f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    # Project status
    report_md += f"## Project Status: {st.session_state.analysis_results.get('project_status', 'UNKNOWN')}\n"
    status_justification = st.session_state.analysis_results.get('status_justification', '')
    if status_justification:
        report_md += f"{status_justification}\n\n"
    
    # Scores
    report_md += "## Scores\n"
    report_md += f"- Dependency Mapping: {st.session_state.analysis_results.get('dependency_mapping_score', 0)}/10\n"
    report_md += f"- Objective Setting: {st.session_state.analysis_results.get('objective_setting_score', 0)}/10\n"
    report_md += f"- Planning Quality: {st.session_state.analysis_results.get('planning_quality_score', 0)}/10\n\n"
    
    # Scope Creep Items
    report_md += "## Scope Creep Items\n"
    scope_creep_items = st.session_state.analysis_results.get('scope_creep_items', [])
    if scope_creep_items:
        for item in scope_creep_items:
            if item:  # Check if item is not empty
                report_md += f"- {item}\n"
    else:
        report_md += "No scope creep items identified.\n"
    
    # Risks and Issues
    report_md += "\n## Top Risks and Issues\n"
    top_risks = st.session_state.analysis_results.get('top_risks_issues', [])
    if top_risks:
        for i, item in enumerate(top_risks, 1):
            if item:  # Check if item is not empty
                report_md += f"{i}. {item}\n"
    else:
        report_md += "No significant risks or issues identified.\n"
    
    # Budget Analysis
    report_md += "\n## Budget Analysis\n"
    if st.session_state.budget_data and st.session_state.budget_data.get("total_budget") is not None:
        report_md += f"Total Budget: ${st.session_state.budget_data['total_budget']:,.2f}\n"
        if st.session_state.budget_data.get("spent") is not None:
            report_md += f"Spent to Date: ${st.session_state.budget_data['spent']:,.2f}\n"
            report_md += f"Remaining: ${st.session_state.budget_data['remaining']:,.2f}\n"
            report_md += f"Status: {st.session_state.budget_data['over_under'].upper()}SPEND\n"
    else:
        budget_analysis = st.session_state.analysis_results.get('budget_analysis', '')
        report_md += f"{budget_analysis if budget_analysis else 'No budget information available'}\n"
    
    # Dependency Mapping Analysis
    dependency_mapping_reasoning = st.session_state.analysis_results.get('dependency_mapping_reasoning', '')
    if dependency_mapping_reasoning:
        report_md += f"\n## Dependency Mapping Analysis\n{dependency_mapping_reasoning}\n"
    
    # Objective Setting Analysis
    objective_setting_reasoning = st.session_state.analysis_results.get('objective_setting_reasoning', '')
    if objective_setting_reasoning:
        report_md += f"\n## Objective Setting Analysis\n{objective_setting_reasoning}\n"
    
    # Good Objectives Examples
    report_md += "\n### Good Objectives Examples\n"
    good_objectives = st.session_state.analysis_results.get('objective_examples', {}).get('good', [])
    if good_objectives:
        for ex in good_objectives:
            if ex:  # Check if example is not empty
                report_md += f"- {ex}\n"
    else:
        report_md += "No good objectives examples identified.\n"
    
    # Poor Objectives Examples
    report_md += "\n### Poor Objectives Examples\n"
    poor_objectives = st.session_state.analysis_results.get('objective_examples', {}).get('poor', [])
    if poor_objectives:
        for ex in poor_objectives:
            if ex:  # Check if example is not empty
                report_md += f"- {ex}\n"
    else:
        report_md += "No poor objectives examples identified.\n"
    
    # Planning Quality Analysis
    planning_quality_reasoning = st.session_state.analysis_results.get('planning_quality_reasoning', '')
    if planning_quality_reasoning:
        report_md += f"\n## Planning Quality Analysis\n{planning_quality_reasoning}\n"
    
    # Safe download button that handles potential None values
    try:
        st.download_button(
            label="Download Report",
            data=report_md,
            file_name=f"project_health_report_{timestamp}.md",
            mime="text/markdown"
        )
    except Exception as e:
        st.error(f"Error generating download: {str(e)}")
        st.info("Please try again or copy the report content manually.")

# Instructions if no files uploaded
if not uploaded_files and not st.session_state.analysis_results:
    st.info("👈 Start by uploading your project documents")
    
    with st.expander("Sample Project Documents"):
        st.markdown("""
        For best results, include:
        
        1. **Statement of Work** - The original project scope and objectives
        2. **Project Plan** - Timeline, milestones, and task assignments
        3. **Status Reports** - Recent updates on project progress
        4. **Risk & Issue Log** - Known risks and ongoing issues
        5. **Budget Documents** - Financial information and constraints
        6. **Presentations** - Project presentations and slideshows
        
        The application will automatically categorise your documents and extract the most relevant information for analysis.
        """)
