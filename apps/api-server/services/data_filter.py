"""
Data Filter
Filters and cleans event data before sending to client
Migrated from gradio-demo/main.py
"""

import json
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class DataFilter:
    """Filters and cleans event data (migrated from gradio-demo)"""

    def filter_message(self, message: dict) -> dict:
        """
        Filter message to remove unnecessary information.
        Migrated from gradio-demo's filter_message function.
        """
        if message["event"] == "tool_call":
            tool_name = message["data"].get("tool_name")
            tool_input = message["data"].get("tool_input")

            # Filter Google search results
            if (
                tool_name == "google_search"
                and isinstance(tool_input, dict)
                and "result" in tool_input
            ):
                try:
                    result_dict = json.loads(tool_input["result"])
                    if "organic" in result_dict:
                        new_result = {
                            "organic": self._filter_google_search_organic(
                                result_dict["organic"]
                            )
                        }
                        message["data"]["tool_input"]["result"] = json.dumps(
                            new_result, ensure_ascii=False
                        )
                except Exception as e:
                    logger.warning(f"Failed to filter search results: {e}")

            # Filter scrape results
            if (
                tool_name in ["scrape", "scrape_website", "scrape_and_extract_info"]
                and isinstance(tool_input, dict)
                and "result" in tool_input
            ):
                if self._is_scrape_error(tool_input["result"]):
                    message["data"]["tool_input"] = {"error": tool_input["result"]}
                else:
                    # Keep scrape results but remove large content
                    message["data"]["tool_input"] = {}

        return message

    def _filter_google_search_organic(self, organic: List[dict]) -> List[dict]:
        """
        Filter Google search organic results.
        Migrated from gradio-demo's filter_google_search_organic.
        
        Preserves title, link, and snippet for display.
        """
        result = []
        for item in organic:
            result.append(
                {
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),  # Preserve snippet for display
                }
            )
        return result

    def _is_scrape_error(self, result: str) -> bool:
        """
        Check if scrape result is an error.
        Migrated from gradio-demo's is_scrape_error.
        """
        try:
            json.loads(result)
            return False
        except json.JSONDecodeError:
            return True

