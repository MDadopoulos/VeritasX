"""
retrieval_wrappers.py — Counter-wrapper factories for retrieval tools.

Provides factory functions that wrap the raw retrieval tool functions with
per-run call counters. When the limit is exceeded, the wrapped tool returns
{"error": "RETRIEVAL_EXHAUSTED"} instead of calling the underlying function.

The counter resets naturally because each factory call creates a fresh closure.
run_question calls create_agent fresh per question, which calls make_counted_*
fresh, so the counter resets per question (AGT-02 idempotency).

Public API:
    make_counted_route_files(limit=20)      -> StructuredTool
    make_counted_search_in_file(limit=20)   -> StructuredTool
"""

from langchain_core.tools import tool

from src.tools.route_files import _route_files_agent as _raw_route_files_fn
from src.tools.search_in_file import _search_in_file_impl as _raw_search_in_file_fn


def make_counted_route_files(limit: int = 20):
    """
    Create a @tool-decorated route_files that returns RETRIEVAL_EXHAUSTED after `limit` calls.

    Args:
        limit: Maximum number of calls allowed per run. Default 20.

    Returns:
        StructuredTool with name "route_files" and an embedded call counter.
    """
    call_count = {"n": 0}  # mutable container for closure

    @tool("route_files")
    def counted_route_files(question: str) -> dict:
        """
        Extract year references from question and return matching bulletin file paths.

        Args:
            question: The user's question string.

        Returns:
            On success:
                {
                    "paths": [list of absolute path strings that exist on disk],
                    "years_found": [list of {"year": int, "type": str} dicts],
                    "fy_mapped": bool
                }
            On no-year-found:
                {"error": "no_year_found", "question": question}
            When call limit exceeded:
                {"error": "RETRIEVAL_EXHAUSTED"}
        """
        call_count["n"] += 1
        if call_count["n"] > limit:
            return {"error": "RETRIEVAL_EXHAUSTED"}
        return _raw_route_files_fn(question)

    return counted_route_files


def make_counted_search_in_file(limit: int = 20):
    """
    Create a @tool-decorated search_in_file that returns RETRIEVAL_EXHAUSTED after `limit` calls.

    Args:
        limit: Maximum number of calls allowed per run. Default 20.

    Returns:
        StructuredTool with name "search_in_file" and an embedded call counter.
    """
    call_count = {"n": 0}

    @tool("search_in_file")
    def counted_search_in_file(file_path: str, query: str) -> dict:
        """
        Search within a specific file for spans matching the query.

        Uses BM25 ranking with regex fallback. Preserves table boundaries
        (never splits mid-table). Returns ranked text spans.

        Args:
            file_path: Path to the bulletin text file.
            query:     The search query.

        Returns:
            On success (BM25 or regex hits):
                List of dicts, each with:
                    text         – span text
                    source_file  – absolute path to file
                    start_line   – 1-indexed start line
                    end_line     – 1-indexed end line
                    bm25_score   – float BM25 score
                    regex_fallback – bool
            On no results:
                {"error": "no_results", "query": query, "file": file_path, "spans_searched": int}
            When call limit exceeded:
                {"error": "RETRIEVAL_EXHAUSTED"}
        """
        call_count["n"] += 1
        if call_count["n"] > limit:
            return {"error": "RETRIEVAL_EXHAUSTED"}
        return _raw_search_in_file_fn(file_path, query)

    return counted_search_in_file
