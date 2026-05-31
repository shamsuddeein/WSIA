import logging
import os
import openai
from openai import OpenAIError, RateLimitError, APITimeoutError, AuthenticationError

logger = logging.getLogger(__name__)

# Initialize client lazily or handle missing key
def get_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is not set. AI features will be disabled.")
        return None
    return openai.OpenAI(api_key=api_key)

def generate_summary(text):
    """
    Generate a 2-3 sentence summary of the report description.
    Returns None if generation fails or AI is unconfigured.
    """
    client = get_client()
    if not client:
        return None
        
    try:
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': 'Summarize this security incident in 2-3 sentences. Keep it concise, factual, and informative.'},
                {'role': 'user', 'content': text[:2000]} # Cap input to avoid massive token usage
            ],
            max_tokens=150,
            timeout=10,
        )
        return response.choices[0].message.content.strip()
    except AuthenticationError:
        logger.error("OpenAI AuthenticationError: Check your OPENAI_API_KEY.")
    except RateLimitError:
        logger.warning("OpenAI RateLimitError: Throttling requests.")
    except APITimeoutError:
        logger.warning("OpenAI APITimeoutError: Request timed out.")
    except OpenAIError as e:
        logger.error(f"OpenAI Error during summarization: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during summarization: {e}")
        
    return None

def generate_embedding(text):
    """
    Generate a 1536-dimensional embedding using text-embedding-3-small.
    Returns None if generation fails or AI is unconfigured.
    """
    client = get_client()
    if not client:
        return None
        
    try:
        response = client.embeddings.create(
            model='text-embedding-3-small',
            input=[text[:8000]], # Embeddings handle more context, cap at 8k chars safely
            timeout=10,
        )
        return response.data[0].embedding
    except AuthenticationError:
        logger.error("OpenAI AuthenticationError: Check your OPENAI_API_KEY.")
    except RateLimitError:
        logger.warning("OpenAI RateLimitError: Throttling requests.")
    except APITimeoutError:
        logger.warning("OpenAI APITimeoutError: Request timed out.")
    except OpenAIError as e:
        logger.error(f"OpenAI Error during embedding generation: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during embedding generation: {e}")
        
    return None

def suggest_tags(text):
    """
    Suggest exploit pattern tags based on the report description.
    Returns a list of suggested string tags.
    """
    client = get_client()
    if not client:
        return []
        
    try:
        response = client.chat.completions.create(
            model='gpt-4o',
            messages=[
                {'role': 'system', 'content': 'You are a smart contract security expert. Suggest 2 to 5 short tags (e.g., "Flash Loan", "Access Control", "Oracle Manipulation", "Rug Pull") that describe the exploit pattern in the incident. Return ONLY a comma-separated list of tags.'},
                {'role': 'user', 'content': text[:2000]}
            ],
            max_tokens=50,
            timeout=10,
        )
        content = response.choices[0].message.content.strip()
        tags = [t.strip() for t in content.split(',') if t.strip()]
        return tags
    except AuthenticationError:
        logger.error("OpenAI AuthenticationError: Check your OPENAI_API_KEY.")
    except RateLimitError:
        logger.warning("OpenAI RateLimitError: Throttling requests.")
    except APITimeoutError:
        logger.warning("OpenAI APITimeoutError: Request timed out.")
    except OpenAIError as e:
        logger.error(f"OpenAI Error during tag suggestion: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during tag suggestion: {e}")
        
    return []
