Fixtures are generated from consumed real-Provider batch sessions archived under `tmp/` (gitignored). Only machines holding those archived batches can regenerate them.

Regenerate: uv run python -m scripts.acceptance.extract_replay_shapes
