# Legacy: the multithreaded YouTube scraper

This is the project's first generation — a Click CLI (`ScrapeRun.py`) driving a
pool of persistent SeleniumBase browsers (`exec/executor.py`) that scrape
YouTube search results and comments (`utils/YouTubeScraper.py`) to JSON files.
It shares no code with the LangGraph research pipeline in `src/` and is kept
for history.

Run it **from inside this directory** (it resolves `exec`/`utils`/`logs`
relative to its own location):

```bash
cd legacy
make install install-chrome install-chromedriver
make run-scraper

# or directly:
python ScrapeRun.py run-executor \
    --queries "Python programming tutorials" \
    --queries "Machine learning basics" \
    --max-cpu-count 4
```

Dependencies live in `requirements.txt` (separate from the pipeline's
`pyproject.toml`). Caveats: scraping YouTube may violate its Terms of Service;
`YouTubeScraper.search()` is an empty method (search happens via the results
URL); the executor's `class_ref` / `max_cpu_usage` API is more convoluted than
it needs to be.
