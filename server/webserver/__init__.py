"""The RaspTank web/agent layer.

    from webserver.app import app            # Flask app (video, static, /health, /prompt)
    from webserver.registry import registry  # tools the LLM can call
    from webserver.prompts import submit     # one prompt in -> robot action out
"""

from webserver.app import app
from webserver.registry import registry

__all__ = ["app", "registry"]
