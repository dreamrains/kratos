# Confirmation Runtime Stage 2B-2A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route automatic hard questions from `question_need_detector` and answerable legacy `pending_confirmations` through `ConfirmationService`.

**Architecture:** Keep existing detector and advisory producers intact, but replace the Agent Loop auto-suspension storage path. A hard question is adapted into a runtime `QuestionCandidate`, checkpointed, emitted as `SuspendedForConfirmation`, and resumed through the Stage 2B-1 response path. Legacy `pending_confirmations` may remain as producer metadata, but new auto suspensions must not write root `suspension_*.json` files.

**Tech Stack:** Python 3.12, existing confirmation runtime, pytest.

---

## Scope

In scope:

- `_maybe_auto_suspend_for_required_question()` uses `ConfirmationService`.
- `question_need_detector` hard questions and answerable pending confirmations create runtime records.
- Runtime records preserve typed, whitelisted resolution actions.
- Existing direct `ask_user_question` behavior remains unchanged.
- Sync and streaming Agent Loop paths checkpoint runtime confirmations before returning final text.

Out of scope:

- Browser refresh/session API restoration.
- Current-session side panel redesign.
- Full removal of `AnalysisSessionState.pending_confirmations`.
- Reworking multi-file relationship classification or wording.
- Global final-answer guard across legacy advisory producers that have not yet migrated to runtime.

## Tasks

- [x] Add failing tests proving auto suspension writes `confirmations/events.jsonl`, exposes `confirmation_id/version`, and does not write root `suspension_*.json`.
- [x] Add a runtime adapter for automatic required questions with source/operation metadata distinct from direct `ask_user_question`.
- [x] Cut `_maybe_auto_suspend_for_required_question()` to use the runtime adapter and service checkpoint.
- [x] Update legacy execution-control expectations so producer metadata remains, but runtime owns suspension identity.
- [x] Run focused confirmation/execution tests and commit.
