Fixtures are generated from consumed real-Provider batch sessions archived under `tmp/` (gitignored). Only machines holding those archived batches can regenerate them. Each fixture records JSON tool-message payloads plus the harvested `tool_outputs/*_detail.json` structured results (analysis methods, sandbox outputs, error shapes) that evidence projection consumes.

Regenerate: uv run python -m scripts.acceptance.extract_replay_shapes
