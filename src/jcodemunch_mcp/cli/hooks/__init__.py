"""Claude Code hook handlers for jCodemunch enforcement.

One module per hook family; this facade re-exports the ``run_*`` entry
points (server.py dispatch) and the helpers tests exercise directly.
"""

from ._common import (  # noqa: F401
    _CODE_EXTENSIONS,
    _emit_additional_context,
    _norm_path,
    _note_transcript_root,
    _repo_owner_name,
)
from .steering import (  # noqa: F401
    _MIN_SIZE_BYTES,
    run_pretooluse,
)
from .reindex import (  # noqa: F401
    _self_invocation,
    run_copilot_posttooluse,
    run_posttooluse,
)
from .landmarks import _build_landmark_section  # noqa: F401
from .snapshot import run_precompact, run_sessionstart  # noqa: F401
from .taskcomplete import run_taskcomplete  # noqa: F401
from .briefing import _tool_surface, run_subagentstart  # noqa: F401
