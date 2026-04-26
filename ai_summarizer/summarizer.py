"""Summarizer module for NWS forecast discussions."""

import os
from typing import Dict, Any
from openai import OpenAI

# Client configuration for Ollama Cloud Pro
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
if not OLLAMA_API_KEY:
    raise ValueError("OLLAMA_API_KEY environment variable is not set")

FAST_MODEL_CLIENT = OpenAI(
    base_url="https://ollama.com/v1",
    api_key=OLLAMA_API_KEY
)


def summarize_with_fast_model(text: str) -> str:
    """
    Summarize text using the minimax-m2.5 fast model via Ollama Cloud Pro.
    
    Args:
        text: Text to summarize
        
    Returns:
        AI-generated summary string (3-4 bullets)
    """
    if not text or text.strip() == "":
        return "No content to summarize"
    
    # Truncate if too long for API
    if len(text) > 20000:
        text = text[:20000]
    
    try:
        response = FAST_MODEL_CLIENT.chat.completions.create(
            model="minimax-m2.5",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert meteorologist who summarizes NWS forecast discussions. Extract the key driving weather patterns and provide a 3-4 bullet summary."
                },
                {
                    "role": "user",
                    "content": f"Analyze this NWS forecast discussion and provide a 3-4 bullet summary of the key driving weather patterns:\n\n{text}"
                }
            ],
            temperature=0.3
        )
        
        if response.choices and len(response.choices) > 0:
            message = response.choices[0].message
            
            # Check for content first (standard case)
            if hasattr(message, 'content') and message.content:
                return message.content.strip()
            
            # Fallback: minimax-m2.5 returns reasoning_content instead of content
            if hasattr(message, 'reasoning') and message.reasoning:
                return message.reasoning.strip()
        
        return "No summary generated"
        
    except Exception as e:
        error_msg = f"[Fast model error: {type(e).__name__}]"
        print(f"  {error_msg}")
        return error_msg


class HermesSummarizer:
    """
    Summarizes NWS forecast discussions using fast model (minimax-m2.5) for all summarization.
    The fast model handles parsing the AFD structure and extracting relevant content.
    """
    
    def __init__(self, api_key: str = None, local_url: str = None, base_url: str = "https://api.hermes.nousresearch.com/v1"):
        self.api_key = api_key or os.environ.get("OLLAMA_API_KEY", "")
        if not self.api_key:
            raise ValueError("OLLAMA_API_KEY environment variable is not set")
        self.base_url = base_url
        self.local_url = local_url
        self._cache = {}
    
    def generate_summary(
        self,
        text: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        include_keywords: bool = True,
    ) -> str:
        """Generate a summary using the fast model."""
        return summarize_with_fast_model(text)
