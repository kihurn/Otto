"""Phase 0, check 5 (optional): up-to-date answers with Ollama web search.

Searches the web through Ollama, then hands the results to Gemma through C0RE to answer.
Needs an Ollama API key in OLLAMA_API_KEY (README step 3b). Skips itself if it isn't set.

Run:  python check_websearch.py
      python check_websearch.py "who won the last f1 race"
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

from otto_check.common import CLOUD_MODELS, C0REError, Results, chat, fix_for, info, require_key, title

DEFAULT_QUESTION = "Who is the current president of the United States?"


def web_search(query: str, key: str, max_results: int = 3) -> list[dict]:
    req = urllib.request.Request(
        "https://ollama.com/api/web_search",
        data=json.dumps({"query": query, "max_results": max_results}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode()).get("results", [])


def main() -> None:
    question = " ".join(sys.argv[1:]) or DEFAULT_QUESTION
    res = Results("websearch")
    title("Ollama web search")
    key = os.environ.get("OLLAMA_API_KEY", "").strip()
    if not key:
        res.noted("Skipped", "OLLAMA_API_KEY is not set (optional, see README step 3b)")
        res.save()
        return

    try:
        t0 = time.perf_counter()
        results = web_search(question, key)
        secs = time.perf_counter() - t0
        res.passed("Web search works", f"{len(results)} results in {secs:.1f}s")
        for r in results:
            info(f"- {r.get('title', '?')[:70]}  ({r.get('url', '')[:60]})")
    except urllib.error.HTTPError as e:
        fix = "Check the key at https://ollama.com/settings/keys" if e.code in (401, 403) else None
        res.failed("Web search works", f"HTTP {e.code}", fix)
        res.save()
        return
    except Exception as e:
        res.failed("Web search works", f"{type(e).__name__}: {e}"[:200])
        res.save()
        return

    if not require_key(res):
        res.save()
        return
    title("Answering with the search results")
    context = "\n\n".join(f"[{i + 1}] {r.get('title', '')}\n{(r.get('content') or '')[:1500]}"
                          for i, r in enumerate(results))
    prompt = (f"Use these web search results to answer the question in one sentence.\n\n"
              f"{context}\n\nQuestion: {question}")
    model = CLOUD_MODELS[0]
    try:
        answer, secs = chat(model, prompt)
        res.passed(f"{model} answers from the results", f"{secs:.1f}s")
        info(f"Q: {question}")
        info(f"A: {answer[:300]}")
        res.numbers["answer"] = {"question": question, "answer": answer[:500]}
    except C0REError as e:
        res.failed(f"{model} answers from the results", f"{e.code}: {e.message[:200]}", fix_for(e))
    res.save()


if __name__ == "__main__":
    main()
