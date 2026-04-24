import config


def search_web(query: str, max_results: int = 5) -> list:
    if not config.TAVILY_API_KEY:
        return []
    from tavily import TavilyClient
    client = TavilyClient(api_key=config.TAVILY_API_KEY)
    response = client.search(query=query, max_results=max_results)
    return response.get("results", [])
