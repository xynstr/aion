from ddgs import DDGS
import json

def test_search():
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text("latest AI news", max_results=3))
            print(json.dumps(results))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    test_search()
