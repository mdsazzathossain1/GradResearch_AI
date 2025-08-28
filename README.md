**GradResearch AI** - PhD Application Email Generator\
GradResearch AI is an intelligent agent that helps students draft personalized and compelling emails to professors for PhD admission. The system uses advanced web scraping and AI analysis to research professors, analyze alignment with the student's background, and generate highly personalized application emails.

**Features**
🔍 Comprehensive Professor Research: Automatically extracts research information from multiple sources including Google Scholar, institutional profiles, and academic publications\
📄 CV Analysis: Processes and analyzes your CV to extract relevant skills, experience, and projects\
🎯 Research Alignment Analysis: Analyzes the alignment between your background and the professor's research interests\
📧 Personalized Email Generation: Creates compelling, personalized emails tailored to each professor\
🔗 Position Requirements Extraction: Automatically extracts requirements from PhD position postings\
🌐 Flexible Web Scraping: Uses Firecrawl API with fallback to BeautifulSoup for maximum compatibility\
💾 Session Management: Saves research sessions and chat history for future reference\
**Prerequisites**
Before you begin, ensure you have the following installed:

Python 3.10 or higher\
Google API Key (for Gemini AI model)\
Firecrawl API Key (for web scraping) - Optional but recommended\
Git (for version control)\
**Installation**
**1. Clone the Repository**
git clone https://github.com/yourusername/gradresearch-ai.git \
cd gradresearch-ai\
**2. Create and Activate Virtual Environment**
On Windows:\
Create virtual environment\
python -m venv venv

**Activate virtual environment**
venv\Scripts\activate
On macOS/Linux:
Create virtual environment\
python3 -m venv venv

Activate virtual environment\
source venv/bin/activate

**3. Upgrade pip and Install Dependencies**
Upgrade pip to the latest version\
pip install --upgrade pip

Install all required dependencies\
pip install -r requirements.tx

**4. Set Up Environment Variables**
Create a .env file in the root directory of the project:
On Windows:
Create .env file\
echo. > .env
On macOS/Linux:
Create .env file\
touch .env

**Add the following environment variables to your .env file:**
GOOGLE_API_KEY=your_google_api_key_here\
FIRECRAWL_API_KEY=your_firecrawl_api_key_here\

**Getting API Keys:**
Google API Key:
Go to Google AI Studio\
Create a new API key for the Gemini model\
Add it to your .env file\
Firecrawl API Key :\
Go to Firecrawl\
Sign up and get an API key\
Add it to your .env file\
**5. Prepare Your CV**\
Place your CV in PDF format in the root directory of the project and name it cv.pdf. The system will automatically load and process your CV when you start a session.
Then the project structure will be like:\
gradresearch-ai\
├── cv.pdf              # Your CV file\
├── .env                 # Environment variables\
├── requirements.txt     # Python dependencies\
├── main.py             # Main application file\
├── tools.py            # Research and scraping tools\
├── model.py            # AI model configuration\
├── system_prompt.py    # System prompt for the AI\
└── templates/          # HTML templates\
**Usage**
**Starting the Application**
Make sure your virtual environment is activated before running:
**On Windows:**
venv\Scripts\activate

**On macOS/Linux:**
source venv/bin/activate\

**Run the FastAPI application**\
python main.py 
**The application will start on http://localhost:8000**\

**Using the Web Interface**
Open your browser and navigate to http://localhost:8000\
Click "Start Session"\
Use the chat interface to:
Request comprehensive research on the professor\
Analyze alignment with your background\
Generate personalized emails\
Ask for specific information\

**Here are some example prompts you can use:**
**Research a professor**
"Research Professor John Smith from MIT Computer Science and generate a personalized email"\

**Analyze alignment**
"Analyze how my background aligns with Professor Jane Doe's research on machine learning"\

**Generate email for specific position**
"Generate an email for the PhD position at https://example.com/phd-position  for Professor Alan Turing"\

**Extract position requirements**
"Extract requirements from this PhD position: https://example.com/phd-position "\

**Getting Help**
If you encounter issues:

Check the console output for error messages\
Verify your virtual environment is activated\
Verify your API keys are correctly set\
Ensure all dependencies are installed\
Check that your CV is properly formatted and named\
Review the troubleshooting steps above\
**Debug Mode**
For debugging, you can run the application with verbose logging:\
**Run with verbose output**
uvicorn main:app --host 0.0.0.0 --port 8000 --log-level debug\

**Customization**
Modifying the System Prompt\
You can customize the AI's behavior by editing system_prompt.py. The system prompt controls:

Email structure and formatting\
Research methodology\
Tone and style of generated emails\
Adding New Research Sources\
To add new research sources, modify the tools.py file:\

Add new scraping functions in the scrape_academic_content() family\
Update the determine_source_type() function\
Add new search patterns in the search functions\
Customizing Email Templates\
Email generation is handled by the generate_personalized_email() function in tools.py. You can modify:

Email structure\
Tone and formality\
Sections included in the email\

**Contributing**
Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.\
**Development Setup**
1. Fork the repository
2. Clone your fork locally
3. Create and activate virtual environment:
python -m venv venv
On Windows: venv\Scripts\activate
On macOS/Linux: source venv/bin/activate
4. Install development dependencies:
pip install -r requirements.txt
5. Create a feature branch:
git checkout -b feature/amazing-feature
6. Make your changes
7. Test your changes thoroughly
8. Commit your changes:
git commit -m 'Add some amazing feature'
9. Push to the branch
git push origin feature/amazing-feature
10. Open a Pull Request

**Acknowledgments**\
**LangChain** for the AI framework\
**FastAPI** for the web framework\
**Firecrawl** for web scraping capabilities\
**Google Gemini** for the AI model\

**Contact**
If you have any questions or suggestions, please open an issue on GitHub or contact the project maintainer.

**Quick Start Summary**\
For those who want to get started quickly:\
**Clone and navigate**\
git clone https://github.com/yourusername/gradresearch-ai.git 
cd gradresearch-ai
Create and activate virtual environment
python -m venv venv
Windows: venv\Scripts\activate
macOS/Linux: source venv/bin/activate

Install dependencies\
pip install -r requirements.txt

Set up environment variables\
echo GOOGLE_API_KEY=your_key_here > .env

Add your CV as cv.pdf

Run the application
python main.py

