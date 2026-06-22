import os
import sys

# Add webui/ to path before any webui module is imported.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "webui"))

# Set env defaults required by module-level initialisation.
os.environ.setdefault("CONFIG_FILE", "/tmp/jca-test-config.json")
os.environ.setdefault("SNAPCAST_HOST", "127.0.0.1")
os.environ.setdefault("AGENT_API_KEY", "test-key-abc123")
os.environ.setdefault("IMAGE_SHA", "abc1234test0000000000000000000000000000")
os.environ.setdefault("GITHUB_REPO", "test/jca")
os.environ.setdefault("IMAGE_NAME", "ghcr.io/test/jca:test")
os.environ.setdefault("CONTAINER_NAME", "jca-test")
