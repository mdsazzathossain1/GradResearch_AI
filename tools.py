# tools.py (Enhanced with flexible web scraping from any source)
import os
import re
import logging
import time
import json
import requests
from typing import Dict, List, Optional, Any, Tuple
from langchain.tools import tool
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from model import get_embedding_engine
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import quote, urljoin, urlparse, parse_qs
import random

# Try to import Firecrawl
try:
    from firecrawl import Firecrawl
    FIRECRAWL_AVAILABLE = True
except ImportError:
    FIRECRAWL_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables
vector_store = None

def get_retry_session():
    """Create a requests session with retry capabilities"""
    session = requests.Session()
    retry = Retry(
        total=3,
        read=3,
        connect=3,
        backoff_factor=0.3,
        status_forcelist=(500, 502, 504)
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def get_random_user_agent():
    """Get a random user agent to avoid detection"""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0',
        'Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0'
    ]
    return random.choice(user_agents)

def search_web(query: str, num_results: int = 10, search_type: str = "general") -> List[Dict[str, str]]:
    """
    Search the web using various methods based on search type
    search_type: "general", "academic", "scholar", "institutional"
    """
    try:
        session = get_retry_session()
        headers = {
            'User-Agent': get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Modify query based on search type
        if search_type == "scholar":
            search_query = f"{query} site:scholar.google.com"
        elif search_type == "academic":
            search_query = f"{query} (pdf OR article OR paper OR publication OR research)"
        elif search_type == "institutional":
            search_query = f"{query} (university OR institute OR college OR faculty)"
        else:
            search_query = query
        
        # Construct search URL
        search_url = f"https://www.google.com/search?q={quote(search_query)}&num={num_results}"
        
        response = session.get(search_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        search_divs = soup.find_all('div', class_='g')
        
        for div in search_divs[:num_results]:
            try:
                title_elem = div.find('h3')
                link_elem = div.find('a')
                snippet_elem = div.find('div', class_='VwiC3b')
                
                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    link = link_elem.get('href', '')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''
                    
                    # Clean up Google's redirect URLs
                    if link.startswith('/url?q='):
                        link = link.split('/url?q=')[1].split('&sa=U')[0]
                    
                    if link and link.startswith('http'):
                        results.append({
                            'title': title,
                            'link': link,
                            'snippet': snippet,
                            'source_type': determine_source_type(link)
                        })
            except Exception as e:
                logger.warning(f"Error parsing search result: {e}")
                continue
        
        return results
        
    except Exception as e:
        logger.error(f"Error in web search: {e}")
        return []

def determine_source_type(url: str) -> str:
    """Determine the type of source based on URL"""
    url_lower = url.lower()
    
    if 'scholar.google.com' in url_lower:
        return "scholar"
    elif any(domain in url_lower for domain in ['arxiv.org', 'pubmed.ncbi.nlm.nih.gov', 'ieee.org', 'acm.org']):
        return "academic"
    elif any(domain in url_lower for domain in ['.edu', '.ac.uk', '.edu.au']):
        return "institutional"
    elif '.pdf' in url_lower:
        return "pdf"
    elif any(keyword in url_lower for keyword in ['journal', 'paper', 'article', 'publication']):
        return "publication"
    else:
        return "general"

def scrape_academic_content(url: str) -> Dict[str, Any]:
    """Scrape academic content from various sources"""
    try:
        content = enhanced_scrape_website(url)
        if content.startswith("Failed to scrape"):
            return {"error": content}
        
        # Extract academic information
        academic_info = {
            "title": "",
            "authors": "",
            "abstract": "",
            "journal": "",
            "year": "",
            "doi": "",
            "keywords": [],
            "content_type": "",
            "full_text": content
        }
        
        # Determine content type based on URL and content
        url_lower = url.lower()
        if 'arxiv.org' in url_lower:
            academic_info["content_type"] = "arxiv"
            academic_info.update(extract_arxiv_info(content))
        elif 'pubmed.ncbi.nlm.nih.gov' in url_lower:
            academic_info["content_type"] = "pubmed"
            academic_info.update(extract_pubmed_info(content))
        elif 'scholar.google.com' in url_lower:
            academic_info["content_type"] = "scholar"
            academic_info.update(extract_scholar_info(content))
        else:
            academic_info["content_type"] = "general"
            academic_info.update(extract_general_academic_info(content))
        
        return academic_info
        
    except Exception as e:
        logger.error(f"Error scraping academic content: {e}")
        return {"error": str(e)}

def extract_arxiv_info(content: str) -> Dict[str, Any]:
    """Extract information from arXiv papers"""
    info = {}
    
    try:
        # Extract title
        title_match = re.search(r'<h1[^>]*class="title[^"]*"[^>]*>(.*?)</h1>', content, re.IGNORECASE)
        if title_match:
            info["title"] = BeautifulSoup(title_match.group(1), 'html.parser').get_text(strip=True)
        
        # Extract authors
        authors_match = re.search(r'<div[^>]*class="authors[^"]*"[^>]*>(.*?)</div>', content, re.IGNORECASE)
        if authors_match:
            info["authors"] = BeautifulSoup(authors_match.group(1), 'html.parser').get_text(strip=True)
        
        # Extract abstract
        abstract_match = re.search(r'<blockquote[^>]*class="abstract[^"]*"[^>]*>(.*?)</blockquote>', content, re.IGNORECASE)
        if abstract_match:
            info["abstract"] = BeautifulSoup(abstract_match.group(1), 'html.parser').get_text(strip=True)
        
        # Extract year
        year_match = re.search(r'\b(19|20)\d{2}\b', content)
        if year_match:
            info["year"] = year_match.group(0)
        
    except Exception as e:
        logger.warning(f"Error extracting arXiv info: {e}")
    
    return info

def extract_pubmed_info(content: str) -> Dict[str, Any]:
    """Extract information from PubMed articles"""
    info = {}
    
    try:
        # Extract title
        title_match = re.search(r'<h1[^>]*class="heading-title[^"]*"[^>]*>(.*?)</h1>', content, re.IGNORECASE)
        if title_match:
            info["title"] = BeautifulSoup(title_match.group(1), 'html.parser').get_text(strip=True)
        
        # Extract authors
        authors_match = re.search(r'<div[^>]*class="authors-list[^"]*"[^>]*>(.*?)</div>', content, re.IGNORECASE)
        if authors_match:
            info["authors"] = BeautifulSoup(authors_match.group(1), 'html.parser').get_text(strip=True)
        
        # Extract abstract
        abstract_match = re.search(r'<div[^>]*class="abstract-content[^"]*"[^>]*>(.*?)</div>', content, re.IGNORECASE)
        if abstract_match:
            info["abstract"] = BeautifulSoup(abstract_match.group(1), 'html.parser').get_text(strip=True)
        
        # Extract DOI
        doi_match = re.search(r'doi\.org/[^\s<>"{}|\\^`\[\]]+', content)
        if doi_match:
            info["doi"] = doi_match.group(0)
        
    except Exception as e:
        logger.warning(f"Error extracting PubMed info: {e}")
    
    return info

def extract_scholar_info(content: str) -> Dict[str, Any]:
    """Extract information from Google Scholar"""
    info = {}
    
    try:
        # Extract title
        title_match = re.search(r'<h3[^>]*class="gs_rt"[^>]*>(.*?)</h3>', content, re.IGNORECASE)
        if title_match:
            info["title"] = BeautifulSoup(title_match.group(1), 'html.parser').get_text(strip=True)
        
        # Extract authors and publication info
        authors_match = re.search(r'<div[^>]*class="gs_a"[^>]*>(.*?)</div>', content, re.IGNORECASE)
        if authors_match:
            authors_text = BeautifulSoup(authors_match.group(1), 'html.parser').get_text(strip=True)
            info["authors"] = authors_text.split('-')[0].strip()
            
            # Extract year
            year_match = re.search(r'\b(19|20)\d{2}\b', authors_text)
            if year_match:
                info["year"] = year_match.group(0)
        
        # Extract abstract/snippet
        abstract_match = re.search(r'<div[^>]*class="gs_rs"[^>]*>(.*?)</div>', content, re.IGNORECASE)
        if abstract_match:
            info["abstract"] = BeautifulSoup(abstract_match.group(1), 'html.parser').get_text(strip=True)
        
    except Exception as e:
        logger.warning(f"Error extracting Scholar info: {e}")
    
    return info

def extract_general_academic_info(content: str) -> Dict[str, Any]:
    """Extract information from general academic websites"""
    info = {}
    
    try:
        # Extract title using multiple patterns
        title_patterns = [
            r'<h1[^>]*>(.*?)</h1>',
            r'<title[^>]*>(.*?)</title>',
            r'<div[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</div>',
            r'<h2[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</h2>',
        ]
        
        for pattern in title_patterns:
            title_match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if title_match:
                info["title"] = BeautifulSoup(title_match.group(1), 'html.parser').get_text(strip=True)
                break
        
        # Extract abstract using multiple patterns
        abstract_patterns = [
            r'<div[^>]*class="[^"]*abstract[^"]*"[^>]*>(.*?)</div>',
            r'<section[^>]*class="[^"]*abstract[^"]*"[^>]*>(.*?)</section>',
            r'<h2[^>]*>Abstract</h2>(.*?)(?=<h2|$)',
            r'<div[^>]*class="[^"]*summary[^"]*"[^>]*>(.*?)</div>',
            r'Abstract\s*[:\-]?\s*(.*?)(?=\n\n|\n\s*\n|Keywords|Introduction)',
        ]
        
        for pattern in abstract_patterns:
            abstract_match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if abstract_match:
                abstract_text = abstract_match.group(1)
                info["abstract"] = BeautifulSoup(abstract_text, 'html.parser').get_text(strip=True)
                break
        
        # Extract authors
        authors_patterns = [
            r'<div[^>]*class="[^"]*authors?[^"]*"[^>]*>(.*?)</div>',
            r'<span[^>]*class="[^"]*authors?[^"]*"[^>]*>(.*?)</span>',
            r'<p[^>]*class="[^"]*authors?[^"]*"[^>]*>(.*?)</p>',
            r'Authors?\s*[:\-]?\s*(.*?)(?=\n\n|\n\s*\n|Abstract)',
        ]
        
        for pattern in authors_patterns:
            authors_match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if authors_match:
                authors_text = authors_match.group(1)
                info["authors"] = BeautifulSoup(authors_text, 'html.parser').get_text(strip=True)
                break
        
        # Extract year
        year_match = re.search(r'\b(19|20)\d{2}\b', content)
        if year_match:
            info["year"] = year_match.group(0)
        
        # Extract DOI
        doi_match = re.search(r'doi\.org/[^\s<>"{}|\\^`\[\]]+', content)
        if doi_match:
            info["doi"] = doi_match.group(0)
        
        # Extract keywords
        keywords_patterns = [
            r'<div[^>]*class="[^"]*keywords?[^"]*"[^>]*>(.*?)</div>',
            r'<meta[^>]*name="keywords"[^>]*content="([^"]*)"',
            r'Keywords?\s*[:\-]?\s*(.*?)(?=\n\n|\n\s*\n|Introduction)',
        ]
        
        for pattern in keywords_patterns:
            keywords_match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if keywords_match:
                keywords_text = keywords_match.group(1)
                keywords = BeautifulSoup(keywords_text, 'html.parser').get_text(strip=True)
                info["keywords"] = [k.strip() for k in re.split(r'[,;]', keywords) if k.strip()]
                break
        
    except Exception as e:
        logger.warning(f"Error extracting general academic info: {e}")
    
    return info

def scrape_institutional_profile(url: str) -> Dict[str, Any]:
    """Scrape institutional profile information"""
    try:
        content = enhanced_scrape_website(url)
        if content.startswith("Failed to scrape"):
            return {"error": content}
        
        profile_info = {
            "name": "",
            "position": "",
            "department": "",
            "institution": "",
            "research_interests": [],
            "publications": [],
            "contact_info": "",
            "lab_website": "",
            "bio": "",
            "full_content": content
        }
        
        # Extract name
        name_patterns = [
            r'<h1[^>]*>(.*?)</h1>',
            r'<div[^>]*class="[^"]*name[^"]*"[^>]*>(.*?)</div>',
            r'<span[^>]*class="[^"]*name[^"]*"[^>]*>(.*?)</span>',
        ]
        
        for pattern in name_patterns:
            name_match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if name_match:
                profile_info["name"] = BeautifulSoup(name_match.group(1), 'html.parser').get_text(strip=True)
                break
        
        # Extract position
        position_patterns = [
            r'<div[^>]*class="[^"]*position[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</div>',
            r'<span[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</span>',
        ]
        
        for pattern in position_patterns:
            position_match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if position_match:
                profile_info["position"] = BeautifulSoup(position_match.group(1), 'html.parser').get_text(strip=True)
                break
        
        # Extract department
        dept_patterns = [
            r'<div[^>]*class="[^"]*department[^"]*"[^>]*>(.*?)</div>',
            r'Department\s*[:\-]?\s*(.*?)(?=\n\n|\n\s*\n|College|School)',
        ]
        
        for pattern in dept_patterns:
            dept_match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if dept_match:
                profile_info["department"] = BeautifulSoup(dept_match.group(1), 'html.parser').get_text(strip=True)
                break
        
        # Extract research interests
        interests_patterns = [
            r'<div[^>]*class="[^"]*interests?[^"]*"[^>]*>(.*?)</div>',
            r'<h[2-3][^>]*>Research Interests?</h[2-3]>(.*?)(?=<h[2-3]|$)',
            r'Research Interests?\s*[:\-]?\s*(.*?)(?=\n\n|\n\s*\n|Education)',
        ]
        
        for pattern in interests_patterns:
            interests_match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if interests_match:
                interests_text = BeautifulSoup(interests_match.group(1), 'html.parser').get_text(strip=True)
                profile_info["research_interests"] = [i.strip() for i in re.split(r'[,;\n]', interests_text) if i.strip()]
                break
        
        # Extract bio
        bio_patterns = [
            r'<div[^>]*class="[^"]*bio[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*about[^"]*"[^>]*>(.*?)</div>',
            r'<p[^>]*class="[^"]*bio[^"]*"[^>]*>(.*?)</p>',
        ]
        
        for pattern in bio_patterns:
            bio_match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if bio_match:
                profile_info["bio"] = BeautifulSoup(bio_match.group(1), 'html.parser').get_text(strip=True)
                break
        
        # Extract contact info
        contact_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', content)
        if contact_match:
            profile_info["contact_info"] = contact_match.group(1)
        
        # Extract lab website
        lab_url_match = re.search(r'(https?://[^\s<>"{}|\\^`\[\]]*lab[^\s<>"{}|\\^`\[\]]*)', content, re.IGNORECASE)
        if lab_url_match:
            profile_info["lab_website"] = lab_url_match.group(1)
        
        return profile_info
        
    except Exception as e:
        logger.error(f"Error scraping institutional profile: {e}")
        return {"error": str(e)}

@tool
def initialize_vectorstore_with_cv(cv_path: str, api_key: str) -> str:
    """Initialize the knowledge base from a CV in PDF format"""
    global vector_store
    try:
        if not os.path.exists(cv_path):
            return f"Error: CV file not found at {cv_path}"
        loader = PyPDFLoader(cv_path)
        documents = loader.load()
        embeddings = get_embedding_engine(api_key=api_key)
        vector_store = FAISS.from_documents(documents, embeddings)
        return "Successfully loaded and processed the CV."
    except Exception as e:
        logger.error(f"Failed to initialize vector store: {str(e)}")
        return f"Failed to initialize vector store: {e}"

@tool
def search_cv(query: str) -> str:
    """Search the loaded CV for relevant information"""
    global vector_store
    if vector_store is None:
        return "CV has not been loaded yet. Please upload the CV first."
    try:
        results = vector_store.similarity_search(query, k=5)
        formatted_results = []
        for i, doc in enumerate(results, 1):
            formatted_results.append(f"Result {i}:\n{doc.page_content}\n")
        return "\n".join(formatted_results)
    except Exception as e:
        logger.error(f"Failed to search CV: {str(e)}")
        return f"Failed to search CV: {e}"

@tool
def comprehensive_professor_research(professor_name: str, institution: str = "", 
                                   department: str = "", max_papers: int = 10) -> str:
    """
    Extract comprehensive research information about a professor from multiple sources
    including web search, Google Scholar, institutional pages, and journal articles.
    
    Args:
        professor_name: Full name of the professor
        institution: Institution name (optional)
        department: Department name (optional)
        max_papers: Maximum number of papers to extract details for
    """
    logger.info(f"Starting comprehensive research for: {professor_name}")
    
    research_data = {
        "professor_name": professor_name,
        "institution": institution,
        "department": department,
        "papers": [],
        "research_interests": [],
        "citations": 0,
        "h_index": 0,
        "i10_index": 0,
        "institutional_profile": "",
        "lab_website": "",
        "recent_projects": []
    }
    
    try:
        # 1. Get Google Scholar information using web scraping
        scholar_data = extract_google_scholar_data(professor_name, institution)
        if scholar_data:
            research_data.update(scholar_data)
        
        # 2. Get institutional profile information
        if institution:
            institutional_data = extract_institutional_profile_info(professor_name, institution, department)
            if institutional_data:
                research_data.update(institutional_data)
        
        # 3. Get additional web search results
        web_search_data = extract_web_search_research(professor_name, institution)
        if web_search_data:
            research_data.update(web_search_data)
        
        # 4. Extract detailed paper information for top papers
        if research_data["papers"]:
            detailed_papers = extract_detailed_paper_info(research_data["papers"][:max_papers])
            research_data["papers"] = detailed_papers
        
        # 5. Format the comprehensive research data
        return format_research_data(research_data)
        
    except Exception as e:
        logger.error(f"Error in comprehensive professor research: {str(e)}")
        return f"Error extracting comprehensive research data: {str(e)}"

def extract_google_scholar_data(professor_name: str, institution: str) -> Dict[str, Any]:
    """Extract data from Google Scholar using web scraping"""
    try:
        # Search for professor profile
        search_query = f"{professor_name} {institution} Google Scholar"
        search_results = search_web(search_query, num_results=5, search_type="scholar")
        
        scholar_url = None
        for result in search_results:
            if "scholar.google.com" in result['link']:
                scholar_url = result['link']
                break
        
        if not scholar_url:
            logger.warning(f"Could not find Google Scholar profile for {professor_name}")
            return {}
        
        # Scrape scholar profile
        scholar_content = enhanced_scrape_website(scholar_url)
        if scholar_content.startswith("Failed to scrape"):
            return {}
        
        return parse_scholar_data(scholar_content)
        
    except Exception as e:
        logger.error(f"Error extracting Google Scholar data: {str(e)}")
        return {}

def parse_scholar_data(scholar_data: str) -> Dict[str, Any]:
    """Parse Google Scholar data into structured format"""
    try:
        data = {
            "papers": [],
            "research_interests": [],
            "citations": 0,
            "h_index": 0,
            "i10_index": 0
        }
        
        # Extract citation metrics
        citations_match = re.search(r'Citations\s+(\d+)', scholar_data)
        if citations_match:
            data["citations"] = int(citations_match.group(1))
        
        h_index_match = re.search(r'h-index\s+(\d+)', scholar_data)
        if h_index_match:
            data["h_index"] = int(h_index_match.group(1))
        
        i10_index_match = re.search(r'i10-index\s+(\d+)', scholar_data)
        if i10_index_match:
            data["i10_index"] = int(i10_index_match.group(1))
        
        # Extract research interests
        interests_match = re.search(r'Interests\s*:\s*(.*?)(?=\n\n|\n[A-Z]|\Z)', scholar_data, re.DOTALL)
        if interests_match:
            interests = interests_match.group(1).strip()
            data["research_interests"] = [interest.strip() for interest in interests.split(',') if interest.strip()]
        
        # Extract papers
        papers_section = re.search(r'(Articles|Publications)(.*?)(?=\n\n\n|\Z)', scholar_data, re.DOTALL)
        if papers_section:
            papers_text = papers_section.group(2)
            paper_entries = re.findall(r'(.*?)(?=\n\n|\n\d{4}|\Z)', papers_text, re.DOTALL)
            
            for entry in paper_entries:
                paper_info = extract_paper_info_from_text(entry)
                if paper_info:
                    data["papers"].append(paper_info)
        
        return data
        
    except Exception as e:
        logger.error(f"Error parsing scholar data: {str(e)}")
        return {}

def extract_paper_info_from_text(text: str) -> Dict[str, Any]:
    """Extract paper information from text"""
    try:
        # Extract title (usually first line, often in quotes or bold)
        title_match = re.search(r'^["\']?(.*?)["\']?$', text.strip(), re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
        else:
            title = text.strip().split('\n')[0].strip()
        
        # Extract authors (usually after title, before journal/year)
        authors_match = re.search(r'(.*?)\s*(\d{4})', text)
        if authors_match:
            authors = authors_match.group(1).strip()
            year = authors_match.group(2)
        else:
            authors = ""
            year = ""
        
        # Extract citations
        citations_match = re.search(r'Cited by\s+(\d+)', text)
        citations = int(citations_match.group(1)) if citations_match else 0
        
        return {
            "title": title,
            "authors": authors,
            "journal": "",
            "year": year,
            "citations": citations,
            "abstract": "",
            "url": ""
        }
        
    except Exception as e:
        logger.error(f"Error extracting paper info: {str(e)}")
        return {}

def extract_institutional_profile_info(professor_name: str, institution: str, department: str) -> Dict[str, Any]:
    """Extract institutional profile information"""
    try:
        data = {
            "institutional_profile": "",
            "lab_website": "",
            "recent_projects": []
        }
        
        # Search for institutional profile
        search_query = f"{professor_name} {institution} {department} profile faculty"
        search_results = search_web(search_query, num_results=5, search_type="institutional")
        
        for result in search_results:
            url = result['link']
            if institution.lower().replace(' ', '') in url.lower() or 'edu' in url:
                # Scrape the institutional page
                profile_data = scrape_institutional_profile(url)
                if profile_data and not profile_data.get("error"):
                    data["institutional_profile"] = profile_data.get("bio", "")
                    data["lab_website"] = profile_data.get("lab_website", "")
                    
                    # Extract research interests from profile
                    if profile_data.get("research_interests"):
                        data["recent_projects"] = profile_data["research_interests"][:5]
                    
                    break
        
        return data
        
    except Exception as e:
        logger.error(f"Error extracting institutional profile: {str(e)}")
        return {}

def extract_web_search_research(professor_name: str, institution: str) -> Dict[str, Any]:
    """Extract additional research information from web search"""
    try:
        data = {
            "additional_papers": [],
            "news_mentions": [],
            "collaborations": []
        }
        
        # Search for recent publications and news
        search_queries = [
            f"{professor_name} {institution} recent publications",
            f"{professor_name} {institution} research news",
            f"{professor_name} {institution} collaborations"
        ]
        
        for query in search_queries:
            search_results = search_web(query, num_results=3, search_type="academic")
            for result in search_results:
                url = result['link']
                if any(keyword in url.lower() for keyword in ['pdf', 'article', 'paper', 'publication']):
                    data["additional_papers"].append(url)
                elif any(keyword in url.lower() for keyword in ['news', 'press', 'media']):
                    data["news_mentions"].append(url)
        
        return data
        
    except Exception as e:
        logger.error(f"Error extracting web search research: {str(e)}")
        return {}

def extract_detailed_paper_info(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract detailed information including abstracts for papers"""
    detailed_papers = []
    
    for paper in papers:
        try:
            # Search for paper abstract
            abstract = extract_paper_abstract(paper["title"], paper["authors"])
            
            # Find paper URL
            paper_url = find_paper_url(paper["title"], paper["authors"])
            
            paper["abstract"] = abstract
            paper["url"] = paper_url
            
            detailed_papers.append(paper)
            
            # Small delay to avoid rate limiting
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error extracting details for paper {paper['title']}: {str(e)}")
            detailed_papers.append(paper)  # Add paper even if details extraction failed
    
    return detailed_papers

def extract_paper_abstract(title: str, authors: str) -> str:
    """Extract paper abstract using various methods"""
    try:
        # Method 1: Search for paper and extract from search results
        search_query = f"{title} {authors} abstract"
        search_results = search_web(search_query, num_results=3, search_type="academic")
        
        for result in search_results:
            url = result['link']
            if any(keyword in url.lower() for keyword in ['pdf', 'article', 'paper', 'publication']):
                # Scrape the article page
                article_data = scrape_academic_content(url)
                if article_data.get("abstract"):
                    return article_data["abstract"]
        
        return ""
        
    except Exception as e:
        logger.error(f"Error extracting paper abstract: {str(e)}")
        return ""

def find_paper_url(title: str, authors: str) -> str:
    """Find paper URL using search"""
    try:
        search_query = f"{title} {authors} PDF"
        search_results = search_web(search_query, num_results=3, search_type="academic")
        
        for result in search_results:
            url = result['link']
            if url.endswith('.pdf') or any(keyword in url.lower() for keyword in ['edu', 'org', 'gov']):
                return url
        
        return ""
        
    except Exception as e:
        logger.error(f"Error finding paper URL: {str(e)}")
        return ""

def enhanced_scrape_website(url: str) -> str:
    """Enhanced website scraping with Firecrawl and fallback"""
    try:
        # Try Firecrawl first
        if FIRECRAWL_AVAILABLE and os.getenv("FIRECRAWL_API_KEY"):
            try:
                app = Firecrawl(api_key=os.getenv("FIRECRAWL_API_KEY"))
                scraped_data = app.scrape(url, formats=["markdown"], onlyMainContent=True)
                
                if isinstance(scraped_data, dict):
                    if 'data' in scraped_data and 'markdown' in scraped_data['data']:
                        return scraped_data['data']['markdown']
                    elif 'markdown' in scraped_data:
                        return scraped_data['markdown']
                
                return str(scraped_data)
            except Exception as e:
                logger.warning(f"Firecrawl failed: {str(e)}")
        
        # Fallback to requests/BeautifulSoup
        session = get_retry_session()
        headers = {
            'User-Agent': get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()
        
        # Try to find main content
        main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content')
        if not main_content:
            main_content = soup.find('body')
        
        text = main_content.get_text() if main_content else soup.get_text()
        
        # Clean up text
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text
        
    except Exception as e:
        logger.error(f"Failed to scrape {url}: {str(e)}")
        return f"Failed to scrape {url}: {str(e)}"

def format_research_data(research_data: Dict[str, Any]) -> str:
    """Format comprehensive research data into readable string"""
    try:
        formatted = f"""
=== COMPREHENSIVE RESEARCH PROFILE ===
Professor: {research_data['professor_name']}
Institution: {research_data['institution']}
Department: {research_data['department']}
=== CITATION METRICS ===
Total Citations: {research_data['citations']}
h-index: {research_data['h_index']}
i10-index: {research_data['i10_index']}
=== RESEARCH INTERESTS ===
{', '.join(research_data['research_interests']) if research_data['research_interests'] else 'Not specified'}
=== TOP PUBLICATIONS ===
"""
        
        for i, paper in enumerate(research_data['papers'][:5], 1):
            formatted += f"""
{i}. {paper['title']}
   Authors: {paper['authors']}
   Year: {paper['year']}
   Citations: {paper['citations']}
   Abstract: {paper['abstract'][:300]}...
   URL: {paper['url']}
"""
        
        if research_data['recent_projects']:
            formatted += f"""
=== RECENT PROJECTS ===
"""
            for project in research_data['recent_projects']:
                formatted += f"• {project}\n"
        
        if research_data['lab_website']:
            formatted += f"""
=== LAB WEBSITE ===
{research_data['lab_website']}
"""
        
        return formatted
        
    except Exception as e:
        logger.error(f"Error formatting research data: {str(e)}")
        return f"Error formatting research data: {str(e)}"

@tool
def extract_phd_position_requirements(position_url: str) -> str:
    """Extract PhD position requirements from job posting"""
    try:
        logger.info(f"Extracting PhD position requirements from: {position_url}")
        
        content = enhanced_scrape_website(position_url)
        
        if content.startswith("Failed to scrape"):
            return f"Failed to scrape position URL: {content}"
        
        # Extract position requirements
        requirements = {
            "position_title": "",
            "department": "",
            "institution": "",
            "application_deadline": "",
            "required_qualifications": [],
            "preferred_qualifications": [],
            "research_areas": [],
            "application_materials": [],
            "contact_info": ""
        }
        
        # Extract position title
        title_match = re.search(r'(PhD Position|PhD Student|Doctoral Position|Graduate Assistant)(.*?)(?=\n|\||-)', content, re.IGNORECASE)
        if title_match:
            requirements["position_title"] = title_match.group(0).strip()
        
        # Extract department and institution
        dept_match = re.search(r'(Department|Faculty|School)(.*?)(?=\n|\||-)', content, re.IGNORECASE)
        if dept_match:
            requirements["department"] = dept_match.group(0).strip()
        
        inst_match = re.search(r'(University|Institute|College)(.*?)(?=\n|\||-)', content, re.IGNORECASE)
        if inst_match:
            requirements["institution"] = inst_match.group(0).strip()
        
        # Extract application deadline
        deadline_match = re.search(r'(Deadline|Application Deadline|Closing Date)(.*?)(?=\n|\||-)', content, re.IGNORECASE)
        if deadline_match:
            requirements["application_deadline"] = deadline_match.group(0).strip()
        
        # Extract qualifications
        qual_section = re.search(r'(Qualifications|Requirements|Eligibility)(.*?)(?=\n\n|\n#|\n##)', content, re.DOTALL | re.IGNORECASE)
        if qual_section:
            qual_text = qual_section.group(2).strip()
            # Split into bullet points or numbered lists
            qualifications = re.findall(r'[•\-\*]?\s*(.*?)(?=\n[•\-\*]|\n\n|\n\d+\.|\Z)', qual_text, re.DOTALL)
            requirements["required_qualifications"] = [q.strip() for q in qualifications if q.strip()]
        
        # Extract research areas
        research_section = re.search(r'(Research Areas|Areas of Study|Field of Study)(.*?)(?=\n\n|\n#|\n##)', content, re.DOTALL | re.IGNORECASE)
        if research_section:
            research_text = research_section.group(2).strip()
            requirements["research_areas"] = [r.strip() for r in research_text.split(',') if r.strip()]
        
        # Extract contact info
        contact_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', content)
        if contact_match:
            requirements["contact_info"] = contact_match.group(1)
        
        # Format the requirements
        formatted_requirements = f"""=== PhD POSITION REQUIREMENTS ===
Position Title: {requirements['position_title']}
Department: {requirements['department']}
Institution: {requirements['institution']}
Application Deadline: {requirements['application_deadline']}
=== REQUIRED QUALIFICATIONS ===
"""
        
        for qual in requirements['required_qualifications']:
            formatted_requirements += f"• {qual}\n"
        
        if requirements['research_areas']:
            formatted_requirements += f"""
=== RESEARCH AREAS ===
"""
            for area in requirements['research_areas']:
                formatted_requirements += f"• {area}\n"
        
        if requirements['contact_info']:
            formatted_requirements += f"""
=== CONTACT INFORMATION ===
{requirements['contact_info']}
"""
        
        return formatted_requirements
        
    except Exception as e:
        logger.error(f"Error extracting PhD position requirements: {str(e)}")
        return f"Error extracting position requirements: {str(e)}"

@tool
def analyze_research_alignment(professor_research: str, user_background: str, position_requirements: str = "") -> str:
    """
    Analyze alignment between professor's research and user's background
    """
    try:
        logger.info("Analyzing research alignment")
        
        # Extract key information from professor research
        prof_interests = extract_research_interests(professor_research)
        prof_keywords = extract_keywords(professor_research)
        
        # Extract key information from user background
        user_skills = extract_user_skills(user_background)
        user_experience = extract_user_experience(user_background)
        user_projects = extract_user_projects(user_background)
        
        # Extract position requirements if provided
        position_qualifications = []
        position_research_areas = []
        if position_requirements:
            position_qualifications = extract_position_qualifications(position_requirements)
            position_research_areas = extract_position_research_areas(position_requirements)
        
        # Analyze alignment
        alignment_analysis = {
            "research_interests_alignment": analyze_interests_alignment(prof_interests, user_skills, user_experience),
            "skills_alignment": analyze_skills_alignment(prof_keywords, user_skills),
            "experience_alignment": analyze_experience_alignment(prof_keywords, user_experience),
            "project_alignment": analyze_project_alignment(prof_keywords, user_projects),
            "position_requirements_alignment": analyze_position_requirements_alignment(
                position_qualifications, position_research_areas, user_skills, user_experience
            ) if position_requirements else ""
        }
        
        return format_alignment_analysis(alignment_analysis)
        
    except Exception as e:
        logger.error(f"Error analyzing research alignment: {str(e)}")
        return f"Error analyzing research alignment: {str(e)}"

def extract_research_interests(research_text: str) -> List[str]:
    """Extract research interests from research text"""
    try:
        interests = []
        
        # Look for research interests section
        interests_section = re.search(r'(Research Interests|Areas of Expertise|Research Focus)(.*?)(?=\n\n|\n#|\n##)', research_text, re.DOTALL | re.IGNORECASE)
        if interests_section:
            interests_text = interests_section.group(2).strip()
            # Split by commas, semicolons, or new lines
            interests = re.split(r'[,;\n]', interests_text)
            interests = [interest.strip() for interest in interests if interest.strip()]
        
        return list(set(interests))[:10]  # Return unique interests, max 10
        
    except Exception as e:
        logger.error(f"Error extracting research interests: {str(e)}")
        return []

def extract_keywords(text: str) -> List[str]:
    """Extract keywords from text"""
    try:
        # Common technical keywords in research
        tech_keywords = [
            'machine learning', 'artificial intelligence', 'deep learning', 'neural networks',
            'computer vision', 'natural language processing', 'data science', 'optimization',
            'algorithm', 'modeling', 'simulation', 'analysis', 'design', 'development',
            'research', 'experiment', 'testing', 'validation', 'implementation'
        ]
        
        found_keywords = []
        for keyword in tech_keywords:
            if keyword.lower() in text.lower():
                found_keywords.append(keyword)
        
        # Extract capitalized terms that might be technical terms
        capitalized_terms = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', text)
        found_keywords.extend(capitalized_terms)
        
        return list(set(found_keywords))[:15]  # Return unique keywords, max 15
        
    except Exception as e:
        logger.error(f"Error extracting keywords: {str(e)}")
        return []

def extract_user_skills(user_text: str) -> List[str]:
    """Extract user skills from background text"""
    try:
        skills = []
        
        # Look for skills section
        skills_section = re.search(r'(Skills|Technical Skills|Expertise|Competencies)(.*?)(?=\n\n|\n#|\n##)', user_text, re.DOTALL | re.IGNORECASE)
        if skills_section:
            skills_text = skills_section.group(2).strip()
            skills = re.split(r'[,;\n]', skills_text)
            skills = [skill.strip() for skill in skills if skill.strip()]
        
        # Look for programming languages
        programming_languages = ['Python', 'Java', 'C++', 'JavaScript', 'MATLAB', 'R', 'SQL']
        for lang in programming_languages:
            if lang.lower() in user_text.lower():
                skills.append(lang)
        
        # Look for common technical skills
        tech_skills = ['Machine Learning', 'Deep Learning', 'Data Analysis', 'Statistical Analysis', 
                      'Research', 'Experimental Design', 'Optimization', 'Simulation']
        for skill in tech_skills:
            if skill.lower() in user_text.lower():
                skills.append(skill)
        
        return list(set(skills))[:15]  # Return unique skills, max 15
        
    except Exception as e:
        logger.error(f"Error extracting user skills: {str(e)}")
        return []

def extract_user_experience(user_text: str) -> List[str]:
    """Extract user experience from background text"""
    try:
        experience = []
        
        # Look for experience section
        exp_section = re.search(r'(Experience|Work Experience|Professional Experience)(.*?)(?=\n\n|\n#|\n##)', user_text, re.DOTALL | re.IGNORECASE)
        if exp_section:
            exp_text = exp_section.group(2).strip()
            # Extract job titles and responsibilities
            exp_entries = re.findall(r'([A-Z][a-zA-Z\s]+)(.*?)(?=\n\n|\n[A-Z][a-zA-Z\s]+\n|\Z)', exp_text, re.DOTALL)
            for title, desc in exp_entries:
                experience.append(f"{title.strip()}: {desc.strip()[:100]}...")
        
        return experience[:5]  # Return max 5 experiences
        
    except Exception as e:
        logger.error(f"Error extracting user experience: {str(e)}")
        return []

def extract_user_projects(user_text: str) -> List[str]:
    """Extract user projects from background text"""
    try:
        projects = []
        
        # Look for projects section
        proj_section = re.search(r'(Projects|Research Projects|Academic Projects)(.*?)(?=\n\n|\n#|\n##)', user_text, re.DOTALL | re.IGNORECASE)
        if proj_section:
            proj_text = proj_section.group(2).strip()
            # Extract project titles and descriptions
            proj_entries = re.findall(r'([A-Z][a-zA-Z\s]+)(.*?)(?=\n\n|\n[A-Z][a-zA-Z\s]+\n|\Z)', proj_text, re.DOTALL)
            for title, desc in proj_entries:
                projects.append(f"{title.strip()}: {desc.strip()[:100]}...")
        
        return projects[:5]  # Return max 5 projects
        
    except Exception as e:
        logger.error(f"Error extracting user projects: {str(e)}")
        return []

def extract_position_qualifications(position_text: str) -> List[str]:
    """Extract position qualifications from requirements text"""
    try:
        qualifications = []
        
        # Look for qualifications section
        qual_section = re.search(r'(Qualifications|Requirements|Eligibility)(.*?)(?=\n\n|\n#|\n##)', position_text, re.DOTALL | re.IGNORECASE)
        if qual_section:
            qual_text = qual_section.group(2).strip()
            # Split by bullet points or numbered lists
            qualifications = re.findall(r'[•\-\*]?\s*(.*?)(?=\n[•\-\*]|\n\n|\n\d+\.|\Z)', qual_text, re.DOTALL)
            qualifications = [q.strip() for q in qualifications if q.strip()]
        
        return qualifications[:10]  # Return max 10 qualifications
        
    except Exception as e:
        logger.error(f"Error extracting position qualifications: {str(e)}")
        return []

def extract_position_research_areas(position_text: str) -> List[str]:
    """Extract position research areas from requirements text"""
    try:
        areas = []
        
        # Look for research areas section
        areas_section = re.search(r'(Research Areas|Areas of Study|Field of Study)(.*?)(?=\n\n|\n#|\n##)', position_text, re.DOTALL | re.IGNORECASE)
        if areas_section:
            areas_text = areas_section.group(2).strip()
            areas = re.split(r'[,;\n]', areas_text)
            areas = [area.strip() for area in areas if area.strip()]
        
        return areas[:5]  # Return max 5 areas
        
    except Exception as e:
        logger.error(f"Error extracting position research areas: {str(e)}")
        return []

def analyze_interests_alignment(prof_interests: List[str], user_skills: List[str], user_experience: List[str]) -> str:
    """Analyze alignment between research interests and user background"""
    try:
        alignment_score = 0
        alignment_details = []
        
        # Check skill alignment
        for interest in prof_interests:
            for skill in user_skills:
                if interest.lower() in skill.lower() or skill.lower() in interest.lower():
                    alignment_score += 1
                    alignment_details.append(f"Research interest '{interest}' aligns with your skill '{skill}'")
        
        # Check experience alignment
        for interest in prof_interests:
            for exp in user_experience:
                if interest.lower() in exp.lower():
                    alignment_score += 1
                    alignment_details.append(f"Research interest '{interest}' aligns with your experience")
        
        # Calculate alignment percentage
        max_possible = len(prof_interests) * 2  # Max 2 points per interest (skill + experience)
        alignment_percentage = (alignment_score / max_possible * 100) if max_possible > 0 else 0
        
        result = f"Research Interests Alignment: {alignment_percentage:.1f}%\n"
        for detail in alignment_details[:5]:  # Show top 5 alignments
            result += f"  • {detail}\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing interests alignment: {str(e)}")
        return "Error analyzing interests alignment"

def analyze_skills_alignment(prof_keywords: List[str], user_skills: List[str]) -> str:
    """Analyze alignment between professor keywords and user skills"""
    try:
        aligned_skills = []
        missing_skills = []
        
        for keyword in prof_keywords:
            found = False
            for skill in user_skills:
                if keyword.lower() in skill.lower() or skill.lower() in keyword.lower():
                    aligned_skills.append(f"{keyword} ↔ {skill}")
                    found = True
                    break
            if not found:
                missing_skills.append(keyword)
        
        result = f"Skills Alignment: {len(aligned_skills)}/{len(prof_keywords)} keywords matched\n"
        if aligned_skills:
            result += "Aligned skills:\n"
            for alignment in aligned_skills[:5]:
                result += f"  • {alignment}\n"
        if missing_skills:
            result += f"Potential gaps: {', '.join(missing_skills[:3])}...\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing skills alignment: {str(e)}")
        return "Error analyzing skills alignment"

def analyze_experience_alignment(prof_keywords: List[str], user_experience: List[str]) -> str:
    """Analyze alignment between professor keywords and user experience"""
    try:
        relevant_experience = []
        
        for keyword in prof_keywords:
            for exp in user_experience:
                if keyword.lower() in exp.lower():
                    relevant_experience.append(f"{keyword}: {exp}")
        
        result = f"Experience Alignment: {len(relevant_experience)} relevant experiences found\n"
        for exp in relevant_experience[:3]:
            result += f"  • {exp}\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing experience alignment: {str(e)}")
        return "Error analyzing experience alignment"

def analyze_project_alignment(prof_keywords: List[str], user_projects: List[str]) -> str:
    """Analyze alignment between professor keywords and user projects"""
    try:
        relevant_projects = []
        
        for keyword in prof_keywords:
            for project in user_projects:
                if keyword.lower() in project.lower():
                    relevant_projects.append(f"{keyword}: {project}")
        
        result = f"Project Alignment: {len(relevant_projects)} relevant projects found\n"
        for project in relevant_projects[:3]:
            result += f"  • {project}\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing project alignment: {str(e)}")
        return "Error analyzing project alignment"

def analyze_position_requirements_alignment(position_qualifications: List[str], 
                                           position_research_areas: List[str],
                                           user_skills: List[str], 
                                           user_experience: List[str]) -> str:
    """Analyze alignment with position requirements"""
    try:
        met_qualifications = []
        unmet_qualifications = []
        
        for qual in position_qualifications:
            met = False
            for skill in user_skills:
                if qual.lower() in skill.lower() or skill.lower() in qual.lower():
                    met_qualifications.append(f"{qual} ✓")
                    met = True
                    break
            if not met:
                for exp in user_experience:
                    if qual.lower() in exp.lower():
                        met_qualifications.append(f"{qual} ✓")
                        met = True
                        break
            if not met:
                unmet_qualifications.append(f"{qual} ✗")
        
        # Check research areas alignment
        aligned_areas = []
        for area in position_research_areas:
            for skill in user_skills:
                if area.lower() in skill.lower() or skill.lower() in area.lower():
                    aligned_areas.append(f"{area} ↔ {skill}")
                    break
        
        result = f"Position Requirements Alignment: {len(met_qualifications)}/{len(position_qualifications)} qualifications met\n"
        if met_qualifications:
            result += "Met qualifications:\n"
            for qual in met_qualifications:
                result += f"  • {qual}\n"
        if unmet_qualifications:
            result += "Unmet qualifications:\n"
            for qual in unmet_qualifications:
                result += f"  • {qual}\n"
        if aligned_areas:
            result += "Research area alignment:\n"
            for area in aligned_areas:
                result += f"  • {area}\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing position requirements alignment: {str(e)}")
        return "Error analyzing position requirements alignment"

def format_alignment_analysis(alignment_analysis: Dict[str, str]) -> str:
    """Format alignment analysis into readable string"""
    try:
        formatted = "=== RESEARCH ALIGNMENT ANALYSIS ===\n\n"
        
        for key, value in alignment_analysis.items():
            if value:
                formatted += f"{value}\n\n"
        
        return formatted
        
    except Exception as e:
        logger.error(f"Error formatting alignment analysis: {str(e)}")
        return "Error formatting alignment analysis"

@tool
def generate_personalized_email(
    professor_name: str,
    professor_research: str,
    user_background: str,
    position_requirements: str = "",
    additional_context: str = "",
    alignment_analysis: str = ""
) -> str:
    """
    Generate a highly personalized email based on comprehensive research analysis
    """
    try:
        logger.info("Generating personalized email")
        
        # Extract key information
        prof_info = extract_professor_summary(professor_research)
        user_info = extract_user_summary(user_background)
        
        # Generate email components
        subject_line = generate_subject_line(prof_info, user_info, position_requirements)
        
        introduction = generate_introduction(professor_name, prof_info, user_info)
        
        research_interest_section = generate_research_interest_section(prof_info, alignment_analysis)
        
        background_alignment_section = generate_background_alignment_section(user_info, alignment_analysis)
        
        position_requirements_section = ""
        if position_requirements:
            position_requirements_section = generate_position_requirements_section(position_requirements, alignment_analysis)
        
        closing_section = generate_closing_section(user_info, additional_context)
        
        # Combine all sections
        email = f"""{subject_line}
{introduction}
{research_interest_section}
{background_alignment_section}
{position_requirements_section}
{closing_section}
Best regards,
{user_info.get('name', 'Your Name')}
{user_info.get('contact_info', '')}
"""
        
        return email
        
    except Exception as e:
        logger.error(f"Error generating personalized email: {str(e)}")
        return f"Error generating personalized email: {str(e)}"

def extract_professor_summary(research_text: str) -> Dict[str, str]:
    """Extract professor summary from research text"""
    try:
        summary = {
            'name': '',
            'institution': '',
            'department': '',
            'research_interests': '',
            'key_papers': '',
            'recent_projects': ''
        }
        
        # Extract basic info
        name_match = re.search(r'Professor:\s*(.*?)(?=\n)', research_text)
        if name_match:
            summary['name'] = name_match.group(1).strip()
        
        inst_match = re.search(r'Institution:\s*(.*?)(?=\n)', research_text)
        if inst_match:
            summary['institution'] = inst_match.group(1).strip()
        
        dept_match = re.search(r'Department:\s*(.*?)(?=\n)', research_text)
        if dept_match:
            summary['department'] = dept_match.group(1).strip()
        
        # Extract research interests
        interests_match = re.search(r'RESEARCH INTERESTS\s*\n(.*?)(?=\n\n)', research_text, re.DOTALL)
        if interests_match:
            summary['research_interests'] = interests_match.group(1).strip()
        
        # Extract key papers
        papers_section = re.search(r'TOP PUBLICATIONS\s*\n(.*?)(?=\n\n)', research_text, re.DOTALL)
        if papers_section:
            papers_text = papers_section.group(1).strip()
            # Get first 3 papers
            papers = re.findall(r'\d+\.\s*(.*?)(?=\n\s*Authors:)', papers_text)
            summary['key_papers'] = '\n'.join([f"• {paper[:100]}..." for paper in papers[:3]])
        
        # Extract recent projects
        projects_match = re.search(r'RECENT PROJECTS\s*\n(.*?)(?=\n\n)', research_text, re.DOTALL)
        if projects_match:
            summary['recent_projects'] = projects_match.group(1).strip()
        
        return summary
        
    except Exception as e:
        logger.error(f"Error extracting professor summary: {str(e)}")
        return {}

def extract_user_summary(user_text: str) -> Dict[str, str]:
    """Extract user summary from background text"""
    try:
        summary = {
            'name': '',
            'degree': '',
            'institution': '',
            'key_skills': '',
            'relevant_experience': '',
            'notable_projects': '',
            'contact_info': ''
        }
        
        # Extract name (usually at the beginning)
        name_match = re.search(r'^([A-Z][A-Z\s]+[A-Z])$', user_text, re.MULTILINE)
        if name_match:
            summary['name'] = name_match.group(1).strip()
        
        # Extract degree and institution
        degree_match = re.search(r'(BSc|MSc|PhD|Bachelor|Master|Doctorate).*?in.*?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', user_text)
        if degree_match:
            summary['degree'] = degree_match.group(1)
        
        inst_match = re.search(r'([A-Z][a-z]+ (University|Institute|College))', user_text)
        if inst_match:
            summary['institution'] = inst_match.group(1)
        
        # Extract key skills
        skills_section = re.search(r'(Skills|Technical Skills)(.*?)(?=\n\n|\n#|\n##)', user_text, re.DOTALL | re.IGNORECASE)
        if skills_section:
            summary['key_skills'] = skills_section.group(2).strip()[:300]
        
        # Extract relevant experience
        exp_section = re.search(r'(Experience|Work Experience)(.*?)(?=\n\n|\n#|\n##)', user_text, re.DOTALL | re.IGNORECASE)
        if exp_section:
            exp_text = exp_section.group(2).strip()
            # Get first 2 experiences
            experiences = re.findall(r'([A-Z][a-zA-Z\s]+)(.*?)(?=\n\n|\n[A-Z][a-zA-Z\s]+\n|\Z)', exp_text, re.DOTALL)
            summary['relevant_experience'] = '\n'.join([f"• {title}: {desc[:100]}..." for title, desc in experiences[:2]])
        
        # Extract contact info
        contact_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', user_text)
        if contact_match:
            summary['contact_info'] = contact_match.group(1)
        
        return summary
        
    except Exception as e:
        logger.error(f"Error extracting user summary: {str(e)}")
        return {}

def generate_subject_line(prof_info: Dict[str, str], user_info: Dict[str, str], position_requirements: str) -> str:
    """Generate compelling subject line"""
    try:
        if position_requirements:
            return f"Subject: PhD Application - {prof_info.get('name', 'Professor')} - {user_info.get('name', 'Applicant')}"
        else:
            return f"Subject: Research Interest Inquiry - {prof_info.get('name', 'Professor')} - {user_info.get('name', 'Applicant')}"
    except Exception as e:
        logger.error(f"Error generating subject line: {str(e)}")
        return "Subject: PhD Application Inquiry"

def generate_introduction(professor_name: str, prof_info: Dict[str, str], user_info: Dict[str, str]) -> str:
    """Generate email introduction"""
    try:
        introduction = f"""Dear Professor {professor_name.split()[-1] if ' ' in professor_name else professor_name},
I hope this email finds you well. I am writing to express my strong interest in your research at {prof_info.get('institution', 'your institution')}. As a recent {user_info.get('degree', 'graduate')} from {user_info.get('institution', 'my university')}, I have been following your work in {prof_info.get('research_interests', 'your field')} with great admiration."""
        
        return introduction
        
    except Exception as e:
        logger.error(f"Error generating introduction: {str(e)}")
        return "Dear Professor,\n\nI hope this email finds you well. I am writing to express my interest in your research."

def generate_research_interest_section(prof_info: Dict[str, str], alignment_analysis: str) -> str:
    """Generate research interest section"""
    try:
        section = f"""Your research on {prof_info.get('research_interests', 'various topics')} particularly resonates with my academic background and research interests. I have been especially impressed by your recent work, including:
{prof_info.get('key_papers', 'Your notable publications')}
{prof_info.get('recent_projects', 'Your current projects')}
Based on my analysis of your research profile, I believe there is strong alignment between your work and my expertise."""
        
        return section
        
    except Exception as e:
        logger.error(f"Error generating research interest section: {str(e)}")
        return "I am very interested in your research work and believe my background aligns well with your expertise."

def generate_background_alignment_section(user_info: Dict[str, str], alignment_analysis: str) -> str:
    """Generate background alignment section"""
    try:
        section = f"""My background has prepared me well to contribute to your research group. I have developed strong expertise in:
{user_info.get('key_skills', 'Relevant technical skills')}
{user_info.get('relevant_experience', 'Relevant experience')}
{alignment_analysis}
This combination of skills and experience has given me a solid foundation in the methodologies and approaches that are central to your research."""
        
        return section
        
    except Exception as e:
        logger.error(f"Error generating background alignment section: {str(e)}")
        return "My background has prepared me well to contribute to your research group."

def generate_position_requirements_section(position_requirements: str, alignment_analysis: str) -> str:
    """Generate position requirements section"""
    try:
        section = f"""I am particularly interested in the PhD position you have advertised, and I am confident that I meet the key requirements:
{position_requirements}
{alignment_analysis}
I am excited about the opportunity to contribute to your ongoing research projects and believe that my skills and enthusiasm would make me a valuable addition to your team."""
        
        return section
        
    except Exception as e:
        logger.error(f"Error generating position requirements section: {str(e)}")
        return "I am particularly interested in the PhD position and believe I meet the key requirements."

def generate_closing_section(user_info: Dict[str, str], additional_context: str) -> str:
    """Generate email closing"""
    try:
        closing = f"""I would be grateful for the opportunity to discuss how my background and research interests align with your work. Please let me know if you would be available for a brief conversation or if you require any additional information.
{additional_context}
Thank you for your time and consideration. I look forward to hearing from you."""
        
        return closing
        
    except Exception as e:
        logger.error(f"Error generating closing section: {str(e)}")
        return "Thank you for your time and consideration. I look forward to hearing from you."

# Define the TOOLS list
TOOLS = [
    initialize_vectorstore_with_cv,
    search_cv,
    comprehensive_professor_research,
    extract_phd_position_requirements,
    analyze_research_alignment,
    generate_personalized_email
]