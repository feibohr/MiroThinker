# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
Clinical Guideline Search MCP Server

Provides tools to search clinical guidelines and medical practice recommendations
from the Sinohealth medical database.
"""

import asyncio
import json
import os
from typing import List, Optional

import requests
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("clinical-guideline-server")

# API Configuration
MEDICAL_SEARCH_BASE_URL = os.environ.get(
    "MEDICAL_SEARCH_BASE_URL", "https://studio.sinohealth.cn/v1/datasets/medical/search"
)
MEDICAL_SEARCH_API_KEY = os.environ.get("MEDICAL_SEARCH_API_KEY", "")

# Default timeout for HTTP requests (in seconds)
DEFAULT_TIMEOUT = 30.0


@mcp.tool()
async def search_clinical_guideline(
    query: str,
    queries: Optional[List[str]] = None,
    limit: int = 5,
) -> str:
    """Search clinical guidelines database for medical practice guidelines and recommendations.

    This tool searches a comprehensive clinical guidelines database to find
    relevant medical practice guidelines, clinical protocols, and treatment
    recommendations based on the user's query.
    
    Use this tool when you need:
    - Official clinical practice guidelines
    - Standard diagnostic criteria and treatment protocols
    - Evidence-based treatment recommendations
    - Clinical decision-making guidelines
    
    For latest research findings and academic papers,
    use search_medical_literature instead.

    Args:
        query: The main search query (user's current question)
        queries: Optional list of expanded/related queries to improve search results.
                 Can include translations or alternative phrasings.
                 Example: ["糖尿病诊疗指南", "diabetes clinical guideline"]
        limit: Maximum number of results to return (default: 5, max: 20)

    Returns:
        JSON string containing search results in the same format as google_search.
        Compatible with research_web_search component on frontend.
        Each result includes:
        - index: Result index number
        - title: Title of the guideline
        - link: URL to the full guideline
        - snippet: Relevant excerpt from the guideline content
        - icon: Favicon URL (medical icon for all results)

    Example:
        search_clinical_guideline(
            query="糖尿病诊疗指南",
            queries=["2型糖尿病指南", "diabetes management guideline"],
            limit=5
        )
    """
    if not MEDICAL_SEARCH_API_KEY:
        return json.dumps(
            {
                "success": False,
                "error": "MEDICAL_SEARCH_API_KEY not configured. Please set the environment variable.",
                "organic": [],
            },
            ensure_ascii=False,
        )

    # Validate and limit the number of results
    limit = min(max(1, limit), 20)

    # Prepare request payload
    payload = {
        "query": query,
        "queries": queries or [],
        "dsls": {"guideline": {"vikingdb_dsl": {}}},
        "rerank_mode": 1,
        "limit": limit,
        "output_content": True,
    }

    headers = {
        "Authorization": f"Bearer {MEDICAL_SEARCH_API_KEY}",
        "Content-Type": "application/json",
    }

    def _sync_search():
        """Synchronous search function to be run in thread pool"""
        response = requests.post(
            MEDICAL_SEARCH_BASE_URL,
            json=payload,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    
    try:
        # Run synchronous function in thread pool to avoid blocking event loop
        result = await asyncio.to_thread(_sync_search)

        # Format the response to match google_search format
        organic_results = []
        if "records" in result and len(result["records"]) > 0:
            for idx, record in enumerate(result["records"], start=1):
                organic_results.append({
                    "index": idx,
                    "title": record.get("title", "No title"),
                    "link": record.get("url", ""),
                    "snippet": record.get("snippet", ""),
                    "icon": "https://doctor-agent.sinohealth.com/favicon.ico",  # Medical database icon
                    "no_scrape": True  # Mark as no scraping needed (requires login)
                })
            
            return json.dumps(
                {
                    "success": True,
                    "searchParameters": {
                        "q": query,
                        "type": "clinical_guideline",
                        "num": len(organic_results)
                    },
                    "organic": organic_results,
                },
                ensure_ascii=False,
            )
        else:
            return json.dumps(
                {
                    "success": True,
                    "searchParameters": {
                        "q": query,
                        "type": "clinical_guideline",
                        "num": 0
                    },
                    "organic": [],
                },
                ensure_ascii=False,
            )

    except requests.Timeout as e:
        return json.dumps(
            {
                "success": False,
                "error": f"Request timeout after {DEFAULT_TIMEOUT} seconds",
                "error_type": "Timeout",
                "error_details": str(e) or repr(e),
                "organic": [],
            },
            ensure_ascii=False,
        )
    except requests.ConnectionError as e:
        return json.dumps(
            {
                "success": False,
                "error": f"Connection error: Unable to connect to {MEDICAL_SEARCH_BASE_URL}",
                "error_type": "ConnectionError",
                "error_details": str(e) or repr(e),
                "organic": [],
            },
            ensure_ascii=False,
        )
    except requests.HTTPError as e:
        status_code = e.response.status_code if hasattr(e, 'response') and e.response else 'unknown'
        return json.dumps(
            {
                "success": False,
                "error": f"HTTP error occurred: {status_code}",
                "error_type": "HTTPError",
                "error_details": str(e),
                "response_body": e.response.text[:500] if hasattr(e, 'response') and hasattr(e.response, 'text') else '',
                "organic": [],
            },
            ensure_ascii=False,
        )
    except Exception as e:
        error_msg = str(e) if str(e) else repr(e)
        return json.dumps(
            {
                "success": False,
                "error": f"Failed to search clinical guidelines: {error_msg}",
                "error_type": type(e).__name__,
                "error_details": repr(e),
                "organic": [],
            },
            ensure_ascii=False,
        )


if __name__ == "__main__":
    mcp.run(transport="stdio")
