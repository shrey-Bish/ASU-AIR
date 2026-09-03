"""SlideSight -- accessibility remediation for PowerPoint lecture decks.

Finds every image in a .pptx, writes real alt text with a vision model running
on ASU Research Computing hardware, and applies only what the model is
confident about. The rest goes to a human review queue.
"""

from .pipeline import remediate

__version__ = "0.1.0"
__all__ = ["remediate"]
