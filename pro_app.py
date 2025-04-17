import streamlit as st
import pandas as pd
import numpy as np
import datetime
import json
import anthropic
import base64
import io
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.dates as mdates
from io import BytesIO

# --- Authentication Code (Unchanged) ---
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

if not check_password():
    st.stop()
  


# Set page configuration
st.set_page_config(
    page_title="Project Planning Assistant",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 1rem;
    }
    .section-header {
        font-size: 1.8rem;
        font-weight: 600;
        color: #2563EB;
        margin-top: 1.5rem;
        margin-bottom: 0.75rem;
    }
    .subsection-header {
        font-size: 1.4rem;
        font-weight: 500;
        color: #3B82F6;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
    }
    .instruction-text {
        background-color: #EFF6FF;
        padding: 0.75rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .highlight-box {
        background-color: #DBEAFE;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 5px solid #2563EB;
        margin-bottom: 1rem;
    }
    .milestone-box {
        background-color: #FEF3C7;
        padding: 0.5rem;
        border-radius: 0.3rem;
        margin-bottom: 0.5rem;
    }
    .stButton>button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state variables if they don't exist
if 'project_info' not in st.session_state:
    st.session_state.project_info = {
        'name': '',
        'description': '',
        'start_date': datetime.date.today(),
        'end_date': datetime.date.today() + datetime.timedelta(days=90),
        'goals': [],
        'objectives': [],
        'stakeholders': [],
        'constraints': [],
        'assumptions': []
    }

if 'tasks' not in st.session_state:
    st.session_state.tasks = pd.DataFrame(
        columns=['ID', 'Name', 'Description', 'Start Date', 'End Date', 'Duration (days)', 
                 'Dependencies', 'Resources', 'Status', 'Priority', 'Category', 'Milestone', 'Deliverable']
    )

if 'current_task_id' not in st.session_state:
    st.session_state.current_task_id = 1
    
if 'ai_generated_tasks' not in st.session_state:
    st.session_state.ai_generated_tasks = []

if 'ai_generated_plan' not in st.session_state:
    st.session_state.ai_generated_plan = ""
    
if 'ai_loading' not in st.session_state:
    st.session_state.ai_loading = False

# Anthropic API Client
def get_anthropic_client():
    api_key = st.session_state.get("anthropic_api_key", "")
    if api_key:
        return anthropic.Anthropic(api_key=api_key)
    return None

# Function to get project information from Claude
def generate_project_plan(project_info):
    client = get_anthropic_client()
    if not client:
        st.error("Please enter your Anthropic API key to use AI features")
        return ""
    
    # Construct prompt for Claude
    prompt = f"""
    You are an expert project manager. I need you to help me create a comprehensive project plan based on the following project information:
    
    Project Name: {project_info['name']}
    Project Description: {project_info['description']}
    Start Date: {project_info['start_date']}
    End Date: {project_info['end_date']}
    
    Goals:
    {chr(10).join(['- ' + goal for goal in project_info['goals']])}
    
    Objectives:
    {chr(10).join(['- ' + obj for obj in project_info['objectives']])}
    
    Stakeholders:
    {chr(10).join(['- ' + stakeholder for stakeholder in project_info['stakeholders']])}
    
    Constraints:
    {chr(10).join(['- ' + constraint for constraint in project_info['constraints']])}
    
    Assumptions:
    {chr(10).join(['- ' + assumption for assumption in project_info['assumptions']])}
    
    First, provide a high-level project plan with phases and key milestones. Then, provide a detailed list of tasks with the following information for each task:
    - Task Name
    - Task Description
    - Estimated Start Date
    - Estimated End Date
    - Duration (days)
    - Dependencies (what tasks need to be completed before this task can start)
    - Resources needed
    - Priority (High, Medium, Low)
    - Category (e.g., Planning, Design, Development, Testing, Deployment)
    - Is this a milestone? (Yes/No)
    - Associated deliverable (if applicable)
    
    Structure your response in JSON format that can be easily parsed by a Python application. Use the following structure:
    ```json
    {
        "high_level_plan": "Detailed description of the high-level project plan with phases",
        "tasks": [
            {
                "id": 1,
                "name": "Task name",
                "description": "Task description",
                "start_date": "YYYY-MM-DD",
                "end_date": "YYYY-MM-DD",
                "duration": 5,
                "dependencies": [0],
                "resources": "Required resources",
                "priority": "High/Medium/Low",
                "category": "Category name",
                "is_milestone": true/false,
                "deliverable": "Deliverable name (if applicable)"
            },
            // More tasks...
        ]
    }
    ```
    
    Make sure to create a realistic and comprehensive project plan with appropriate dependencies, durations, and milestones.
    """
    
    try:
        response = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=4000,
            temperature=0.2,
            system="You are an expert project manager helping to create detailed project plans. You always respond with well-structured, realistic project plans based on the information provided.",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return response.content[0].text
    except Exception as e:
        st.error(f"Error when communicating with Claude: {str(e)}")
        return ""

# Function to parse the AI-generated plan and extract tasks
def parse_ai_generated_plan(plan_text):
    try:
        # Try to find JSON content between triple backticks
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', plan_text, re.DOTALL)
        
        if json_match:
            json_str = json_match.group(1)
        else:
            # If not found between backticks, try to treat the entire text as JSON
            json_str = plan_text
            
        # Clean up any potential markdown artifacts
        json_str = re.sub(r'\\n', '\n', json_str)
        json_str = re.sub(r'\\r', '', json_str)
        
        plan_data = json.loads(json_str)
        
        high_level_plan = plan_data.get('high_level_plan', '')
        tasks = plan_data.get('tasks', [])
        
        # Convert tasks to DataFrame format
        task_records = []
        for task in tasks:
            task_record = {
                'ID': task.get('id', 0),
                'Name': task.get('name', ''),
                'Description': task.get('description', ''),
                'Start Date': task.get('start_date', ''),
                'End Date': task.get('end_date', ''),
                'Duration (days)': task.get('duration', 0),
                'Dependencies': ', '.join(map(str, task.get('dependencies', []))),
                'Resources': task.get('resources', ''),
                'Status': 'Not Started',
                'Priority': task.get('priority', 'Medium'),
                'Category': task.get('category', ''),
                'Milestone': 'Yes' if task.get('is_milestone', False) else 'No',
                'Deliverable': task.get('deliverable', '')
            }
            task_records.append(task_record)
            
        return high_level_plan, pd.DataFrame(task_records)
    except Exception as e:
        st.error(f"Error parsing AI response: {str(e)}")
        return "", pd.DataFrame()

# Function to create a dependency chart
def create_dependency_chart(tasks_df):
    if tasks_df.empty:
        return None
    
    # Create a directed graph
    G = nx.DiGraph()
    
    # Add nodes (tasks)
    for idx, row in tasks_df.iterrows():
        task_id = row['ID']
        task_name = row['Name']
        is_milestone = row['Milestone'] == 'Yes'
        
        # Add attributes to nodes
        node_color = 'gold' if is_milestone else 'lightblue'
        G.add_node(task_id, name=task_name, color=node_color)
    
    # Add edges (dependencies)
    for idx, row in tasks_df.iterrows():
        task_id = row['ID']
        if pd.notna(row['Dependencies']) and row['Dependencies']:
            # Split dependencies string and convert to integers
            dependencies = [int(dep.strip()) for dep in str(row['Dependencies']).split(',') if dep.strip()]
            for dep in dependencies:
                if dep in G.nodes:
                    G.add_edge(dep, task_id)
    
    # Create a figure
    plt.figure(figsize=(12, 8))
    
    # Define node colors based on milestone status
    node_colors = [G.nodes[n]['color'] for n in G.nodes]
    
    # Define node positions using a layout algorithm
    pos = nx.spring_layout(G, seed=42, k=0.5)
    
    # Draw the nodes
    nx.draw_networkx_nodes(G, pos, node_size=700, node_color=node_colors, alpha=0.8, edgecolors='black')
    
    # Draw the edges
    nx.draw_networkx_edges(G, pos, width=1.5, alpha=0.7, arrows=True, arrowsize=20, edge_color='gray')
    
    # Draw labels
    labels = {n: f"{n}: {G.nodes[n]['name']}" for n in G.nodes}
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=8, font_family='sans-serif')
    
    plt.title("Task Dependencies", fontsize=16)
    plt.axis('off')
    plt.tight_layout()
    
    # Convert the plot to an image
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    plt.close()
    buf.seek(0)
    
    return buf

# Function to create a Gantt chart
def create_gantt_chart(tasks_df):
    if tasks_df.empty:
        return None
    
    # Convert date strings to datetime objects
    tasks_df['Start Date'] = pd.to_datetime(tasks_df['Start Date'])
    tasks_df['End Date'] = pd.to_datetime(tasks_df['End Date'])
    
    # Sort by start date
    tasks_df = tasks_df.sort_values('Start Date')
    
    # Create a figure and axis
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Define colors based on priority
    colors = {'High': '#FF5252', 'Medium': '#4CAF50', 'Low': '#2196F3'}
    milestone_color = '#FFC107'
    
    # Y-axis positions
    y_positions = list(range(len(tasks_df)))
    
    # Plot horizontal bars for each task
    for i, (idx, task) in enumerate(tasks_df.iterrows()):
        start_date = task['Start Date']
        end_date = task['End Date']
        duration = (end_date - start_date).days
        
        if task['Milestone'] == 'Yes':
            # Plot milestone as a diamond
            plt.scatter(start_date, i, marker='D', s=100, color=milestone_color, edgecolors='black', zorder=5)
        else:
            # Plot task as a bar
            priority = task['Priority']
            color = colors.get(priority, '#4CAF50')  # Default to Medium color
            plt.barh(i, duration, left=start_date, height=0.5, color=color, alpha=0.8, edgecolor='black')
    
    # Customize the axis
    plt.yticks(y_positions, tasks_df['Name'])
    plt.grid(axis='x', linestyle='--', alpha=0.7)
    
    # Format x-axis as dates
    date_format = mdates.DateFormatter('%Y-%m-%d')
    ax.xaxis.set_major_formatter(date_format)
    plt.xticks(rotation=45)
    
    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=colors['High'], edgecolor='black', label='High Priority'),
        Patch(facecolor=colors['Medium'], edgecolor='black', label='Medium Priority'),
        Patch(facecolor=colors['Low'], edgecolor='black', label='Low Priority'),
        plt.Line2D([0], [0], marker='D', color='w', markerfacecolor=milestone_color, 
                  markeredgecolor='black', markersize=10, label='Milestone')
    ]
    ax.legend(handles=legend_elements, loc='upper right')
    
    plt.title('Project Gantt Chart', fontsize=16)
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Tasks', fontsize=12)
    plt.tight_layout()
    
    # Convert the plot to an image
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    plt.close()
    buf.seek(0)
    
    return buf

# Function to export project data to CSV
def export_to_csv(project_info, tasks_df):
    # Create a BytesIO object
    output = io.BytesIO()
    
    # Create a writer to write to the BytesIO object
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    
    # Write project info to the first sheet
    project_df = pd.DataFrame([
        ['Project Name', project_info['name']],
        ['Project Description', project_info['description']],
        ['Start Date', project_info['start_date']],
        ['End Date', project_info['end_date']]
    ], columns=['Field', 'Value'])
    
    project_df.to_excel(writer, sheet_name='Project Info', index=False)
    
    # Write goals to a sheet
    goals_df = pd.DataFrame(project_info['goals'], columns=['Goals'])
    goals_df.to_excel(writer, sheet_name='Goals & Objectives', startrow=0, startcol=0, index=False)
    
    # Write objectives to the same sheet
    objectives_df = pd.DataFrame(project_info['objectives'], columns=['Objectives'])
    objectives_df.to_excel(writer, sheet_name='Goals & Objectives', startrow=0, startcol=2, index=False)
    
    # Write stakeholders to a sheet
    stakeholders_df = pd.DataFrame(project_info['stakeholders'], columns=['Stakeholders'])
    stakeholders_df.to_excel(writer, sheet_name='Stakeholders', index=False)
    
    # Write constraints and assumptions to a sheet
    constraints_df = pd.DataFrame(project_info['constraints'], columns=['Constraints'])
    constraints_df.to_excel(writer, sheet_name='Constraints & Assumptions', startrow=0, startcol=0, index=False)
    
    assumptions_df = pd.DataFrame(project_info['assumptions'], columns=['Assumptions'])
    assumptions_df.to_excel(writer, sheet_name='Constraints & Assumptions', startrow=0, startcol=2, index=False)
    
    # Write tasks to a sheet
    tasks_df.to_excel(writer, sheet_name='Tasks', index=False)
    
    # Close the writer
    writer.save()
    
    # Reset the pointer to the start of the BytesIO object
    output.seek(0)
    
    return output

# Function to export to MS Project XML format
def export_to_ms_project(project_info, tasks_df):
    # Create XML structure
    xml_template = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Project xmlns="http://schemas.microsoft.com/project/2010">
    <Name>{project_info['name']}</Name>
    <Title>{project_info['name']}</Title>
    <StartDate>{project_info['start_date']}</StartDate>
    <FinishDate>{project_info['end_date']}</FinishDate>
    <Tasks>
        <Task>
            <UID>0</UID>
            <ID>0</ID>
            <Name>Project Start</Name>
            <Type>0</Type>
            <IsNull>0</IsNull>
            <CreateDate>{project_info['start_date']}</CreateDate>
            <Start>{project_info['start_date']}</Start>
            <Finish>{project_info['start_date']}</Finish>
            <IsManual>0</IsManual>
            <DurationFormat>7</DurationFormat>
            <IsPublished>1</IsPublished>
            <IsExpanded>1</IsExpanded>
        </Task>
    """
    
    # Add tasks
    for idx, task in tasks_df.iterrows():
        # Handle dependencies
        predecessors_str = ""
        if pd.notna(task['Dependencies']) and task['Dependencies']:
            dependencies = [dep.strip() for dep in str(task['Dependencies']).split(',') if dep.strip()]
            if dependencies:
                predecessors = []
                for dep in dependencies:
                    try:
                        predecessors.append(f"<PredecessorLink><PredecessorUID>{dep}</PredecessorUID><Type>1</Type></PredecessorLink>")
                    except:
                        pass
                predecessors_str = ''.join(predecessors)
        
        task_type = "1" if task['Milestone'] == 'Yes' else "0"
        
        xml_template += f"""
        <Task>
            <UID>{task['ID']}</UID>
            <ID>{task['ID']}</ID>
            <Name>{task['Name']}</Name>
            <Notes>{task['Description']}</Notes>
            <Type>{task_type}</Type>
            <IsNull>0</IsNull>
            <CreateDate>{task['Start Date']}</CreateDate>
            <Start>{task['Start Date']}</Start>
            <Finish>{task['End Date']}</Finish>
            <Duration>PT{task['Duration (days)']}D</Duration>
            <DurationFormat>7</DurationFormat>
            <Priority>{task['Priority']}</Priority>
            <IsManual>0</IsManual>
            <IsPublished>1</IsPublished>
            <IsExpanded>1</IsExpanded>
            {predecessors_str}
        </Task>
        """
    
    # Close XML structure
    xml_template += """
    </Tasks>
</Project>
    """
    
    return xml_template.encode()

# Function to download data as a file
def download_button(object_to_download, download_filename, button_text):
    if isinstance(object_to_download, pd.DataFrame):
        object_to_download = object_to_download.to_csv(index=False)
        b64 = base64.b64encode(object_to_download.encode()).decode()
        file_type = 'text/csv'
    elif isinstance(object_to_download, BytesIO):
        b64 = base64.b64encode(object_to_download.getvalue()).decode()
        file_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif isinstance(object_to_download, bytes):
        b64 = base64.b64encode(object_to_download).decode()
        file_type = 'application/xml'
    else:
        b64 = base64.b64encode(object_to_download.encode()).decode()
        file_type = 'text/plain'
    
    href = f'<a href="data:{file_type};base64,{b64}" download="{download_filename}">{button_text}</a>'
    return href

# Add goal functionality
def add_goal():
    if st.session_state.new_goal and st.session_state.new_goal not in st.session_state.project_info['goals']:
        st.session_state.project_info['goals'].append(st.session_state.new_goal)
        st.session_state.new_goal = ""

# Add objective functionality
def add_objective():
    if st.session_state.new_objective and st.session_state.new_objective not in st.session_state.project_info['objectives']:
        st.session_state.project_info['objectives'].append(st.session_state.new_objective)
        st.session_state.new_objective = ""

# Add stakeholder functionality
def add_stakeholder():
    if st.session_state.new_stakeholder and st.session_state.new_stakeholder not in st.session_state.project_info['stakeholders']:
        st.session_state.project_info['stakeholders'].append(st.session_state.new_stakeholder)
        st.session_state.new_stakeholder = ""

# Add constraint functionality
def add_constraint():
    if st.session_state.new_constraint and st.session_state.new_constraint not in st.session_state.project_info['constraints']:
        st.session_state.project_info['constraints'].append(st.session_state.new_constraint)
        st.session_state.new_constraint = ""

# Add assumption functionality
def add_assumption():
    if st.session_state.new_assumption and st.session_state.new_assumption not in st.session_state.project_info['assumptions']:
        st.session_state.project_info['assumptions'].append(st.session_state.new_assumption)
        st.session_state.new_assumption = ""

# Add task functionality
def add_task():
    if st.session_state.new_task_name:
        # Calculate duration
        start_date = st.session_state.new_task_start_date
        end_date = st.session_state.new_task_end_date
        duration = (end_date - start_date).days
        
        # Create new task row
        new_task = {
            'ID': st.session_state.current_task_id,
            'Name': st.session_state.new_task_name,
            'Description': st.session_state.new_task_description,
            'Start Date': start_date,
            'End Date': end_date,
            'Duration (days)': duration,
            'Dependencies': st.session_state.new_task_dependencies,
            'Resources': st.session_state.new_task_resources,
            'Status': 'Not Started',
            'Priority': st.session_state.new_task_priority,
            'Category': st.session_state.new_task_category,
            'Milestone': 'Yes' if st.session_state.new_task_milestone else 'No',
            'Deliverable': st.session_state.new_task_deliverable
        }
        
        # Add to DataFrame
        st.session_state.tasks = pd.concat([st.session_state.tasks, pd.DataFrame([new_task])], ignore_index=True)
        
        # Increment task ID
        st.session_state.current_task_id += 1
        
        # Clear form
        st.session_state.new_task_name = ""
        st.session_state.new_task_description = ""
        st.session_state.new_task_start_date = datetime.date.today()
        st.session_state.new_task_end_date = datetime.date.today() + datetime.timedelta(days=1)
        st.session_state.new_task_dependencies = ""
        st.session_state.new_task_resources = ""
        st.session_state.new_task_priority = "Medium"
        st.session_state.new_task_category = ""
        st.session_state.new_task_milestone = False
        st.session_state.new_task_deliverable = ""

# Delete goal functionality
def delete_goal(goal_idx):
    if 0 <= goal_idx < len(st.session_state.project_info['goals']):
        del st.session_state.project_info['goals'][goal_idx]

# Delete objective functionality
def delete_objective(obj_idx):
    if 0 <= obj_idx < len(st.session_state.project_info['objectives']):
        del st.session_state.project_info['objectives'][obj_idx]

# Delete stakeholder functionality
def delete_stakeholder(stakeholder_idx):
    if 0 <= stakeholder_idx < len(st.session_state.project_info['stakeholders']):
        del st.session_state.project_info['stakeholders'][stakeholder_idx]

# Delete constraint functionality
def delete_constraint(constraint_idx):
    if 0 <= constraint_idx < len(st.session_state.project_info['constraints']):
        del st.session_state.project_info['constraints'][constraint_idx]

# Delete assumption functionality
def delete_assumption(assumption_idx):
    if 0 <= assumption_idx < len(st.session_state.project_info['assumptions']):
        del st.session_state.project_info['assumptions'][assumption_idx]

# Delete task functionality
def delete_task(task_idx):
    st.session_state.tasks = st.session_state.tasks.drop(task_idx).reset_index(drop=True)

# Generate AI plan
def generate_ai_plan():
    st.session_state.ai_loading = True
    st.session_state.ai_generated_plan = generate_project_plan(st.session_state.project_info)
    high_level_plan, tasks_df = parse_ai_generated_plan(st.session_state.ai_generated_plan)
    st.session_state.ai_generated_tasks = tasks_df
    st.session_state.ai_high_level_plan = high_level_plan
    st.session_state.ai_loading = False

# Import AI tasks
def import_ai_tasks():
    if not st.session_state.ai_generated_tasks.empty:
        # Adjust task IDs to avoid conflicts
        max_id = st.session_state.current_task_id
        st.session_state.ai_generated_tasks['ID'] = range(max_id, max_id + len(st.session_state.ai_generated_tasks))
        
        # Append AI tasks to existing tasks
        st.session_state.tasks = pd.concat([st.session_state.tasks, st.session_state.ai_generated_tasks], ignore_index=True)
        
        # Update current task ID
        st.session_state.current_task_id = max(st.session_state.tasks['ID']) + 1 if not st.session_state.tasks.empty else 1
        
        # Clear AI tasks
        st.session_state.ai_generated_tasks = pd.DataFrame()
        st.session_state.ai_generated_plan = ""
        st.success("AI-generated tasks imported successfully!")

# Main application
def main():
    # Title
    st.markdown('<div class="main-header">Project Planning Assistant</div>', unsafe_allow_html=True)
    
    # Create tabs
    tabs = st.tabs(["Project Definition", "Tasks & Timeline", "Visualizations", "Export", "Claude AI Assistant"])
    
    # Tab 1: Project Definition
    with tabs[0]:
        st.markdown('<div class="section-header">Project Information</div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.session_state.project_info['name'] = st.text_input("Project Name", st.session_state.project_info['name'])
            st.session_state.project_info['start_date'] = st.date_input("Start Date", st.session_state.project_info['start_date'])
        
        with col2:
            st.session_state.project_info['description'] = st.text_area("Project Description", st.session_state.project_info['description'])
            st.session_state.project_info['end_date'] = st.date_input("End Date", st.session_state.project_info['end_date'])
        
        # Goals section
        st.markdown('<div class="subsection-header">Project Goals</div>', unsafe_allow_html=True)
        st.markdown('<div class="instruction-text">Define high-level goals that describe what the project aims to achieve.</div>', unsafe_allow_html=True)
        
        # Display existing goals
        for i, goal in enumerate(st.session_state.project_info['goals']):
            cols = st.columns([0.9, 0.1])
            cols[0].markdown(f"- {goal}")
            if cols[1].button("🗑️", key=f"del_goal_{i}"):
                delete_goal(i)
        
        # Add new goal
        st.text_input("Add a new goal", key="new_goal", on_change=add_goal)
        
        # Objectives section
        st.markdown('<div class="subsection-header">Project Objectives</div>', unsafe_allow_html=True)
        st.markdown('<div class="instruction-text">Define specific, measurable objectives that support the project goals.</div>', unsafe_allow_html=True)
        
        # Display existing objectives
        for i, objective in enumerate(st.session_state.project_info['objectives']):
            cols = st.columns([0.9, 0.1])
            cols[0].markdown(f"- {objective}")
            if cols[1].button("🗑️", key=f"del_obj_{i}"):
                delete_objective(i)
        
        # Add new objective
        st.text_input("Add a new objective", key="new_objective", on_change=add_objective)
        
        # Stakeholders section
        st.markdown('<div class="subsection-header">Stakeholders</div>', unsafe_allow_html=True)
        st.markdown('<div class="instruction-text">List all stakeholders involved in or affected by the project.</div>', unsafe_allow_html=True)
        
        # Display existing stakeholders
        for i, stakeholder in enumerate(st.session_state.project_info['stakeholders']):
            cols = st.columns([0.9, 0.1])
            cols[0].markdown(f"- {stakeholder}")
            if cols[1].button("🗑️", key=f"del_stake_{i}"):
                delete_stakeholder(i)
        
        # Add new stakeholder
        st.text_input("Add a new stakeholder", key="new_stakeholder", on_change=add_stakeholder)
        
        # Constraints section
        st.markdown('<div class="subsection-header">Constraints</div>', unsafe_allow_html=True)
        st.markdown('<div class="instruction-text">List project constraints (budget, time, resources, etc.).</div>', unsafe_allow_html=True)
        
        # Display existing constraints
        for i, constraint in enumerate(st.session_state.project_info['constraints']):
            cols = st.columns([0.9, 0.1])
            cols[0].markdown(f"- {constraint}")
            if cols[1].button("🗑️", key=f"del_const_{i}"):
                delete_constraint(i)
        
        # Add new constraint
        st.text_input("Add a new constraint", key="new_constraint", on_change=add_constraint)
        
        # Assumptions section
        st.markdown('<div class="subsection-header">Assumptions</div>', unsafe_allow_html=True)
        st.markdown('<div class="instruction-text">List assumptions made for project planning.</div>', unsafe_allow_html=True)
        
        # Display existing assumptions
        for i, assumption in enumerate(st.session_state.project_info['assumptions']):
            cols = st.columns([0.9, 0.1])
            cols[0].markdown(f"- {assumption}")
            if cols[1].button("🗑️", key=f"del_assump_{i}"):
                delete_assumption(i)
        
        # Add new assumption
        st.text_input("Add a new assumption", key="new_assumption", on_change=add_assumption)
    
    # Tab 2: Tasks & Timeline
    with tabs[1]:
        st.markdown('<div class="section-header">Tasks & Timeline</div>', unsafe_allow_html=True)
        
        # Create columns for task list and task form
        col1, col2 = st.columns([0.6, 0.4])
        
        with col1:
            st.markdown('<div class="subsection-header">Task List</div>', unsafe_allow_html=True)
            
            # Display tasks in a table
            if not st.session_state.tasks.empty:
                edited_df = st.data_editor(
                    st.session_state.tasks,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "ID": st.column_config.NumberColumn("ID", help="Task ID"),
                        "Name": st.column_config.TextColumn("Name", help="Task name"),
                        "Description": st.column_config.TextColumn("Description", help="Task description"),
                        "Start Date": st.column_config.DateColumn("Start Date", help="Task start date"),
                        "End Date": st.column_config.DateColumn("End Date", help="Task end date"),
                        "Duration (days)": st.column_config.NumberColumn("Duration (days)", help="Task duration in days"),
                        "Dependencies": st.column_config.TextColumn("Dependencies", help="Task dependencies (comma-separated IDs)"),
                        "Resources": st.column_config.TextColumn("Resources", help="Resources needed for the task"),
                        "Status": st.column_config.SelectboxColumn("Status", options=["Not Started", "In Progress", "Completed", "Delayed"], help="Task status"),
                        "Priority": st.column_config.SelectboxColumn("Priority", options=["High", "Medium", "Low"], help="Task priority"),
                        "Category": st.column_config.TextColumn("Category", help="Task category"),
                        "Milestone": st.column_config.SelectboxColumn("Milestone", options=["Yes", "No"], help="Is this a milestone?"),
                        "Deliverable": st.column_config.TextColumn("Deliverable", help="Task deliverable")
                    },
                    num_rows="dynamic"
                )
                
                # Update tasks with edited values
                st.session_state.tasks = edited_df
            else:
                st.info("No tasks added yet. Use the form on the right to add tasks.")
        
        with col2:
            st.markdown('<div class="subsection-header">Add Task</div>', unsafe_allow_html=True)
            
            # Task form
            st.text_input("Task Name", key="new_task_name")
            st.text_area("Description", key="new_task_description")
            st.date_input("Start Date", value=datetime.date.today(), key="new_task_start_date")
            st.date_input("End Date", value=datetime.date.today() + datetime.timedelta(days=1), key="new_task_end_date")
            st.text_input("Dependencies (comma-separated IDs)", key="new_task_dependencies")
            st.text_input("Resources", key="new_task_resources")
            st.selectbox("Priority", options=["High", "Medium", "Low"], index=1, key="new_task_priority")
            st.text_input("Category", key="new_task_category")
            st.checkbox("Is this a milestone?", key="new_task_milestone")
            st.text_input("Deliverable", key="new_task_deliverable")
            
            # Add task button
            st.button("Add Task", on_click=add_task, type="primary")
    
    # Tab 3: Visualizations
    with tabs[2]:
        st.markdown('<div class="section-header">Project Visualizations</div>', unsafe_allow_html=True)
        
        # Create tabs for different visualizations
        viz_tabs = st.tabs(["Gantt Chart", "Dependency Chart"])
        
        with viz_tabs[0]:
            st.markdown('<div class="subsection-header">Gantt Chart</div>', unsafe_allow_html=True)
            
            if not st.session_state.tasks.empty:
                gantt_chart = create_gantt_chart(st.session_state.tasks.copy())
                if gantt_chart:
                    st.image(gantt_chart, use_column_width=True)
            else:
                st.info("Add tasks to generate a Gantt chart.")
        
        with viz_tabs[1]:
            st.markdown('<div class="subsection-header">Dependency Chart</div>', unsafe_allow_html=True)
            
            if not st.session_state.tasks.empty:
                dependency_chart = create_dependency_chart(st.session_state.tasks.copy())
                if dependency_chart:
                    st.image(dependency_chart, use_column_width=True)
            else:
                st.info("Add tasks with dependencies to generate a dependency chart.")
    
    # Tab 4: Export
    with tabs[3]:
        st.markdown('<div class="section-header">Export Project Plan</div>', unsafe_allow_html=True)
        
        export_tabs = st.tabs(["Excel Export", "MS Project Export", "CSV Export"])
        
        with export_tabs[0]:
            st.markdown('<div class="subsection-header">Export to Excel</div>', unsafe_allow_html=True)
            st.markdown('<div class="instruction-text">Export your project plan to Excel format for further analysis or sharing.</div>', unsafe_allow_html=True)
            
            if st.button("Generate Excel Export", type="primary"):
                excel_data = export_to_csv(st.session_state.project_info, st.session_state.tasks)
                st.markdown(
                    download_button(excel_data, "project_plan.xlsx", "📥 Download Excel File"),
                    unsafe_allow_html=True
                )
        
        with export_tabs[1]:
            st.markdown('<div class="subsection-header">Export to MS Project XML</div>', unsafe_allow_html=True)
            st.markdown('<div class="instruction-text">Export your project plan to MS Project XML format for import into Microsoft Project.</div>', unsafe_allow_html=True)
            
            if st.button("Generate MS Project XML", type="primary"):
                xml_data = export_to_ms_project(st.session_state.project_info, st.session_state.tasks)
                st.markdown(
                    download_button(xml_data, "project_plan.xml", "📥 Download MS Project XML File"),
                    unsafe_allow_html=True
                )
        
        with export_tabs[2]:
            st.markdown('<div class="subsection-header">Export Tasks to CSV</div>', unsafe_allow_html=True)
            st.markdown('<div class="instruction-text">Export just the tasks to CSV format for import into other tools.</div>', unsafe_allow_html=True)
            
            if st.button("Generate CSV Export", type="primary"):
                st.markdown(
                    download_button(st.session_state.tasks, "project_tasks.csv", "📥 Download CSV File"),
                    unsafe_allow_html=True
                )
    
    # Tab 5: Claude AI Assistant
    with tabs[4]:
        st.markdown('<div class="section-header">Claude AI Project Planning Assistant</div>', unsafe_allow_html=True)
        st.markdown('<div class="instruction-text">Let Claude help you generate a comprehensive project plan based on your inputs.</div>', unsafe_allow_html=True)
        
        # API key input
        if "anthropic_api_key" not in st.session_state:
            st.session_state.anthropic_api_key = ""
        
        api_key = st.text_input(
            "Enter your Anthropic API Key",
            type="password",
            value=st.session_state.anthropic_api_key,
            key="api_key_input"
        )
        
        st.session_state.anthropic_api_key = api_key
        
        # Generate button
        if st.button("Generate AI Project Plan", type="primary", disabled=not st.session_state.anthropic_api_key):
            generate_ai_plan()
        
        # Display loading spinner
        if st.session_state.ai_loading:
            with st.spinner("Claude is generating your project plan..."):
                st.info("This may take a minute. Claude is creating a detailed project plan based on your inputs.")
        
        # Display AI response
        if hasattr(st.session_state, 'ai_high_level_plan') and st.session_state.ai_high_level_plan:
            st.markdown('<div class="subsection-header">AI-Generated Project Plan</div>', unsafe_allow_html=True)
            st.markdown('<div class="highlight-box">' + st.session_state.ai_high_level_plan + '</div>', unsafe_allow_html=True)
            
            if not st.session_state.ai_generated_tasks.empty:
                st.markdown('<div class="subsection-header">AI-Generated Tasks</div>', unsafe_allow_html=True)
                st.dataframe(st.session_state.ai_generated_tasks, use_container_width=True)
                
                if st.button("Import AI Tasks", type="primary"):
                    import_ai_tasks()

if __name__ == "__main__":
    main()
