import os

# Several modules construct an `AsyncOpenAI()` client at import time
# (e.g. src/app/graph/nodes/topicEmbed.py). The OpenAI SDK raises if no key
# is present, which would break test *collection* before any test runs.
# A dummy key is enough — every test that touches OpenAI mocks the client.
os.environ.setdefault("OPENAI_API_KEY", "test-key")
