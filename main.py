# main.py (Fixed Version)
import os
import uuid
import json
from pathlib import Path
import uvicorn
import traceback
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.messages import HumanMessage, AIMessage
from model import get_model
from tools import TOOLS, initialize_vectorstore_with_cv, comprehensive_professor_research, extract_phd_position_requirements, analyze_research_alignment, generate_personalized_email, search_cv
from system_prompt import system_prompt

# Load environment variables
load_dotenv()

# --- Agent Setup ---
google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    raise ValueError("GOOGLE_API_KEY is not set in the environment.")

llm = get_model(api_key=google_api_key)

# Create the agent
agent = create_openai_tools_agent(llm, TOOLS, system_prompt)
agent_executor = AgentExecutor(agent=agent, tools=TOOLS, verbose=True, handle_parsing_errors=True)

# --- FastAPI App ---
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Store conversation threads in memory and persist to disk
conversations = {}
CHAT_HISTORY_FILE = "chat_history.json"

# Load chat history from file if it exists
def load_chat_history():
    global conversations
    try:
        if os.path.exists(CHAT_HISTORY_FILE):
            with open(CHAT_HISTORY_FILE, 'r') as f:
                conversations = json.load(f)
                # Convert string messages back to Message objects
                for thread_id, data in conversations.items():
                    messages = []
                    for msg in data["messages"]:
                        if msg["type"] == "human":
                            messages.append(HumanMessage(content=msg["content"]))
                        elif msg["type"] == "ai":
                            messages.append(AIMessage(content=msg["content"]))
                    conversations[thread_id] = {
                        "config": data.get("config", {}),
                        "messages": messages,
                        "metadata": data.get("metadata", {})
                    }
    except Exception as e:
        print(f"Error loading chat history: {e}")
        conversations = {}

# Save chat history to file
def save_chat_history():
    try:
        # Convert Message objects to serializable format
        serializable_conversations = {}
        for thread_id, data in conversations.items():
            serializable_messages = []
            for msg in data["messages"]:
                if isinstance(msg, HumanMessage):
                    serializable_messages.append({"type": "human", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    serializable_messages.append({"type": "ai", "content": msg.content})
            serializable_conversations[thread_id] = {
                "config": data.get("config", {}),
                "messages": serializable_messages,
                "metadata": data.get("metadata", {})
            }
        
        with open(CHAT_HISTORY_FILE, 'w') as f:
            json.dump(serializable_conversations, f)
    except Exception as e:
        print(f"Error saving chat history: {e}")

# Load chat history on startup
load_chat_history()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/start_session")
async def start_session(
    professor_name: str = Form(None),
    scholar_id: str = Form(None),
    profile_url: str = Form(None),
    program_url: str = Form(None),
    university_name: str = Form(None),
    department_name: str = Form(None),
    position_url: str = Form(None)
):
    thread_id = str(uuid.uuid4())
    print(f"\n--- NEW SESSION STARTED ---")
    print(f"Generated Thread ID: {thread_id}")
    conversations[thread_id] = {
        "config": {"configurable": {"thread_id": thread_id}}, 
        "messages": [],
        "metadata": {}
    }
    print(f"Current conversations: {list(conversations.keys())}")
    
    # Add metadata if provided
    if professor_name:
        conversations[thread_id]["metadata"]["professor_name"] = professor_name
    if scholar_id:
        conversations[thread_id]["metadata"]["scholar_id"] = scholar_id
    if profile_url:
        conversations[thread_id]["metadata"]["profile_url"] = profile_url
    if program_url:
        conversations[thread_id]["metadata"]["program_url"] = program_url
    if university_name:
        conversations[thread_id]["metadata"]["university_name"] = university_name
    if department_name:
        conversations[thread_id]["metadata"]["department_name"] = department_name
    if position_url:
        conversations[thread_id]["metadata"]["position_url"] = position_url
    
    cv_path = "cv.pdf"
    if Path(cv_path).exists():
        print("Found cv.pdf, attempting to load...")
        result = initialize_vectorstore_with_cv.invoke({"cv_path": cv_path, "api_key": google_api_key})
        print(f"CV loading result: {result}")
    else:
        print("cv.pdf not found. CV will need to be loaded manually.")
    
    # Save chat history after creating new session
    save_chat_history()
    
    return {"thread_id": thread_id, "metadata": conversations[thread_id]["metadata"]}

@app.get("/sessions")
async def get_sessions():
    """Get all available conversation sessions"""
    session_list = []
    for thread_id, data in conversations.items():
        # Get the first human message as the session title if available
        title = "New Chat"
        for msg in data["messages"]:
            if isinstance(msg, HumanMessage):
                # Truncate long messages for the title
                title = msg.content[:30] + "..." if len(msg.content) > 30 else msg.content
                break
        
        session_list.append({
            "id": thread_id,
            "title": title,
            "message_count": len(data["messages"])
        })
    
    return {"sessions": session_list}

@app.get("/load_session/{thread_id}")
async def load_session(thread_id: str):
    """Load a specific conversation session"""
    if thread_id not in conversations:
        return {"error": "Session not found"}, 404
    
    # Convert messages to a serializable format for the frontend
    messages = []
    for msg in conversations[thread_id]["messages"]:
        if isinstance(msg, HumanMessage):
            messages.append({"type": "human", "content": msg.content})
        elif isinstance(msg, AIMessage):
            messages.append({"type": "ai", "content": msg.content})
    
    return {
        "thread_id": thread_id,
        "messages": messages,
        "metadata": conversations[thread_id].get("metadata", {})
    }

@app.post("/chat")
async def chat_endpoint(thread_id: str = Form(...), message: str = Form(...)):
    """Handles incoming chat messages and returns the agent's response."""
    if thread_id not in conversations:
        return {"error": "Invalid session ID"}, 400
    
    try:
        # Add the human message to the conversation history
        conversations[thread_id]["messages"].append(HumanMessage(content=message))
        
        # Invoke the agent with the conversation history
        response = agent_executor.invoke({
            "messages": conversations[thread_id]["messages"]
        })
        
        # Add the AI response to the conversation history
        ai_message = AIMessage(content=response["output"])
        conversations[thread_id]["messages"].append(ai_message)
        
        # Save chat history after each message
        save_chat_history()
        
        # Check for web research or comprehensive research logs
        research_logs = []
        error_indicators = [
            "Failed to scrape website",
            "Failed to extract professor information",
            "Failed to extract PhD program information",
            "Failed to extract paper information",
            "Failed to get university information",
            "Failed to get department information",
            "Google Scholar search is not available",
            "Error extracting comprehensive research data",
            "Error extracting position requirements",
            "Error analyzing research alignment",
            "Error generating personalized email"
        ]
        
        web_research_errors = []
        for indicator in error_indicators:
            if indicator in response["output"]:
                web_research_errors.append(indicator)
        
        # Extract research logs if present
        if "=== COMPREHENSIVE RESEARCH PROFILE ===" in response["output"]:
            research_logs.append("=== COMPREHENSIVE RESEARCH PROFILE ===")
            lines = response["output"].split('\n')
            in_research = False
            current_log = []
            
            for line in lines:
                if "=== COMPREHENSIVE RESEARCH PROFILE ===" in line:
                    in_research = True
                    current_log = [line]
                elif in_research:
                    if "=== RESEARCH ALIGNMENT ANALYSIS ===" in line or "=== EMAIL GENERATION ===" in line:
                        research_logs.append('\n'.join(current_log))
                        current_log = [line]
                    elif line.startswith("=== ") and "RESEARCH" not in line and "ALIGNMENT" not in line and "EMAIL" not in line:
                        research_logs.append('\n'.join(current_log))
                        current_log = [line]
                    else:
                        current_log.append(line)
            
            if in_research and current_log:
                research_logs.append('\n'.join(current_log))
        
        if "=== RESEARCH ALIGNMENT ANALYSIS ===" in response["output"]:
            research_logs.append("=== RESEARCH ALIGNMENT ANALYSIS ===")
            lines = response["output"].split('\n')
            in_alignment = False
            current_log = []
            
            for line in lines:
                if "=== RESEARCH ALIGNMENT ANALYSIS ===" in line:
                    in_alignment = True
                    current_log = [line]
                elif in_alignment:
                    if "=== EMAIL GENERATION ===" in line or line.startswith("Subject:"):
                        research_logs.append('\n'.join(current_log))
                        current_log = [line]
                    elif line.startswith("=== ") and "ALIGNMENT" not in line and "EMAIL" not in line:
                        research_logs.append('\n'.join(current_log))
                        current_log = [line]
                    else:
                        current_log.append(line)
            
            if in_alignment and current_log:
                research_logs.append('\n'.join(current_log))
        
        # Prepare response
        response_data = {
            "response": response["output"],
            "research_logs": research_logs if research_logs else [],
            "web_research_errors": web_research_errors if web_research_errors else []
        }
        
        return response_data
    
    except Exception as e:
        # It's wise to keep the traceback for now, just in case.
        print("\n--- AN ERROR OCCURRED IN THE AGENT ---")
        traceback.print_exc()
        print("---------------------------------------")
        return {"error": f"An error occurred: {str(e)}"}, 500

@app.post("/comprehensive_research")
async def comprehensive_research_endpoint(
    thread_id: str = Form(...),
    professor_name: str = Form(...),
    institution: str = Form(None),
    department: str = Form(None),
    position_url: str = Form(None)
):
    """Conduct comprehensive research on a professor and position"""
    if thread_id not in conversations:
        return {"error": "Invalid session ID"}, 400
    
    try:
        print(f"\n=== CONDUCTING COMPREHENSIVE RESEARCH ===")
        print(f"Professor: {professor_name}")
        print(f"Institution: {institution}")
        print(f"Department: {department}")
        print(f"Position URL: {position_url}")
        
        # Conduct comprehensive professor research
        professor_research = comprehensive_professor_research.invoke({
            "professor_name": professor_name,
            "institution": institution,
            "department": department,
            "max_papers": 10
        })
        
        print("=== PROFESSOR RESEARCH COMPLETED ===")
        print(professor_research[:500] + "..." if len(professor_research) > 500 else professor_research)
        
        # Extract position requirements if URL provided
        position_requirements = ""
        if position_url:
            position_requirements = extract_phd_position_requirements.invoke({
                "position_url": position_url
            })
            print("=== POSITION REQUIREMENTS EXTRACTED ===")
            print(position_requirements[:500] + "..." if len(position_requirements) > 500 else position_requirements)
        
        # Get user background from CV
        user_background = ""
        try:
            cv_results = search_cv.invoke({"query": "skills experience education projects"})
            user_background = cv_results
            print("=== USER BACKGROUND EXTRACTED ===")
            print(user_background[:500] + "..." if len(user_background) > 500 else user_background)
        except Exception as e:
            print(f"Error extracting user background: {e}")
            user_background = "CV search failed or CV not loaded"
        
        # Analyze research alignment
        alignment_analysis = analyze_research_alignment.invoke({
            "professor_research": professor_research,
            "user_background": user_background,
            "position_requirements": position_requirements
        })
        
        print("=== ALIGNMENT ANALYSIS COMPLETED ===")
        print(alignment_analysis[:500] + "..." if len(alignment_analysis) > 500 else alignment_analysis)
        
        # Generate personalized email
        personalized_email = generate_personalized_email.invoke({
            "professor_name": professor_name,
            "professor_research": professor_research,
            "user_background": user_background,
            "position_requirements": position_requirements,
            "alignment_analysis": alignment_analysis
        })
        
        print("=== PERSONALIZED EMAIL GENERATED ===")
        print(personalized_email[:500] + "..." if len(personalized_email) > 500 else personalized_email)
        
        print("\n=== COMPREHENSIVE RESEARCH COMPLETE ===")
        
        return {
            "professor_research": professor_research,
            "position_requirements": position_requirements,
            "user_background": user_background,
            "alignment_analysis": alignment_analysis,
            "personalized_email": personalized_email
        }
    
    except Exception as e:
        print("\n--- AN ERROR OCCURRED IN COMPREHENSIVE RESEARCH ---")
        traceback.print_exc()
        print("--------------------------------------------------")
        return {"error": f"An error occurred: {str(e)}"}, 500

@app.post("/update_session")
async def update_session(
    thread_id: str = Form(...),
    professor_name: str = Form(None),
    scholar_id: str = Form(None),
    profile_url: str = Form(None),
    program_url: str = Form(None),
    university_name: str = Form(None),
    department_name: str = Form(None),
    position_url: str = Form(None)
):
    """Updates session information with professor and program details."""
    if thread_id not in conversations:
        return {"error": "Invalid session ID"}, 400
    
    try:
        # Update session metadata
        if "metadata" not in conversations[thread_id]:
            conversations[thread_id]["metadata"] = {}
        
        if professor_name:
            conversations[thread_id]["metadata"]["professor_name"] = professor_name
        if scholar_id:
            conversations[thread_id]["metadata"]["scholar_id"] = scholar_id
        if profile_url:
            conversations[thread_id]["metadata"]["profile_url"] = profile_url
        if program_url:
            conversations[thread_id]["metadata"]["program_url"] = program_url
        if university_name:
            conversations[thread_id]["metadata"]["university_name"] = university_name
        if department_name:
            conversations[thread_id]["metadata"]["department_name"] = department_name
        if position_url:
            conversations[thread_id]["metadata"]["position_url"] = position_url
        
        # Save chat history
        save_chat_history()
        
        return {"status": "Session updated successfully"}
    
    except Exception as e:
        print("\n--- AN ERROR OCCURRED UPDATING SESSION ---")
        traceback.print_exc()
        print("------------------------------------------")
        return {"error": f"An error occurred: {str(e)}"}, 500

@app.post("/clear_history")
async def clear_history():
    """Clear all chat history"""
    global conversations
    conversations = {}
    if os.path.exists(CHAT_HISTORY_FILE):
        os.remove(CHAT_HISTORY_FILE)
    return {"status": "Chat history cleared"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)