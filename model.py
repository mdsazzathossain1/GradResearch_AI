# model.py (Simplified and More Robust Version)

import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

# Load environment variables, although they should already be loaded by main.py
load_dotenv()

def get_model(api_key: str):
    """Gets the ChatGoogleGenerativeAI model."""
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",  # Using the latest flash model
        temperature=0.7,
        google_api_key=api_key
    )

def get_embedding_engine(api_key: str = None):
    """
    Gets the embedding engine using the standard LangChain integration.
    This is more reliable and avoids direct 'google.genai' imports.
    """
    if api_key is None:
        api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        raise ValueError("GOOGLE_API_KEY is not set. Please check your .env file.")

    return GoogleGenerativeAIEmbeddings(
        model="models/embedding-001",  # Correct model name for embeddings
        google_api_key=api_key,
        task_type="retrieval_document"
        # The 'title' parameter is often not needed for retrieval, keeping it simple.
    )

def test_embedding_engine(api_key: str = None):
    """Test if the embedding engine is working properly."""
    try:
        engine = get_embedding_engine(api_key)
        # Test with a simple text
        test_embedding = engine.embed_query("Test text for embedding")
        if test_embedding and len(test_embedding) > 0:
            return (
                True,
                f"✅ Embedding engine working! Generated {len(test_embedding)}-dimensional vector",
            )
        else:
            return False, "❌ Embedding engine returned empty result"
    except Exception as e:
        return False, f"❌ Embedding engine test failed: {str(e)}"