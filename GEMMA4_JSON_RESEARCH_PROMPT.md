# Research Prompt: gemma4-e4b JSON Output Reliability

## Problem Statement

**Model**: `gemma4-e4b` (7.5B, Q8_0 quantized) via Ollama
**Endpoint**: `http://localhost:11434/api/generate` (generate API, not chat)
**Task**: Batch file classification — return a JSON array of objects

## Observed Behavior

When prompted to return JSON, gemma4-e4b frequently outputs **natural language statements** instead of JSON. Here are the actual failure modes observed in production logs:

### Failure Mode 1: Natural Language Refusal
```
Due to the highly fragmented and ambiguous nature of the input (where file paths are truncated or missing, and content blocks are not clearly mapped to specific paths), I cannot provide a definitive,
```
**Impact**: 0% parseable. Model explains why it can't comply instead of returning JSON.

### Failure Mode 2: Markdown Code Fences
```json
[
  {
    "path": "filemind/search.py",
    "category": "code",
    "confidence": 1.0
  },
  ...
]
```
**Impact**: JSON is valid but wrapped in ``` fences. Strippable with regex.

### Failure Mode 3: Alternative Key Names
```json
[
  {
    "file_path": "hub/agents/config/hub_agents_config.json",
    "classification": "config"
  },
  {
    "file_name": "settings.json",
    "category": "ai_project",
    "reasoning": "This file is located within..."
  }
]
```
**Impact**: Uses `file_path`/`file_name` instead of `path`, `classification` instead of `category`. Sometimes adds extra fields like `reasoning`.

### Failure Mode 4: Truncated Output
```json
[{"path":"data/telegram_chat_report_20260315.json","category":"personal","confidence":0.9},{"path":"
```
**Impact**: JSON is cut off mid-string due to `num_predict` limit.

### Failure Mode 5: Empty/Whitespace Response
```
(no output or just whitespace)
```
**Impact**: Nothing to parse.

## Current Prompt (Failing)

```
You are a file classification system. For each file, determine exactly ONE category.

Available categories: code, documentation, research, personal, finance, ai_project, media, config, archive, unknown

Files to classify (use directory path context + content to determine category):
• File: "hub/docs/FILEMIND_MASTER_PLAN.md"
  Dir: hub/docs
  Ext: .md
  Content: Master plan for FileMind project with architecture design

• File: "hub/bridge/cline_bridge/bot.py"
  Dir: hub/bridge/cline_bridge
  Ext: .py
  Content: Telegram bot implementation for Cline bridge

OUTPUT RULES:
1. Return ONLY a JSON array. No explanation, no text, no markdown fences.
2. Every file listed above MUST appear in the output with exact path match.
3. Use the category list ONLY. No other values.

Format: [{"path":"exact path from input","category":"category name","confidence":0.0-1.0}]
```

## Ollama Parameters
```json
{
  "model": "gemma4-e4b",
  "prompt": "<prompt above>",
  "stream": false,
  "options": {
    "temperature": 0.1,
    "num_predict": 2000
  }
}
```

## Batch Size
- Currently: 20 files per batch
- Tested successfully with: 3 files (100% accuracy, correct categories)
- Fails consistently with: 20 files

## Key Observations

1. **Small batches (3 files) work perfectly** — 100% correct classification with clean JSON
2. **Large batches (20 files) fail** — model outputs explanations, alternative keys, or refuses
3. **The model IS capable** — when it does output JSON, the classifications are accurate
4. **The issue is output format compliance** — not classification quality

## Research Questions

1. **Does gemma4-e4b have a known issue with JSON output at scale?** Is there a system prompt format, temperature setting, or Ollama parameter that forces strict JSON output?

2. **Is there a "JSON mode" or "structured output" feature** in Ollama for gemma4-e4b similar to OpenAI's `response_format: {"type": "json_object"}`?

3. **Would switching to the chat API** (`/api/chat`) with proper system/user message separation improve JSON compliance vs the generate API?

4. **Is there a prompt engineering technique** (e.g., few-shot examples, XML delimiters, output templates) that forces gemma4 to comply with JSON-only output?

5. **Would a smaller batch size (5 files) with more API calls** be more reliable than 20 files per call, trading speed for reliability?

6. **Is there a gemma4-specific variant** (like `gemma4-e4b-json` that exists in our Ollama) that's optimized for JSON output?

## What We've Tried

- ✅ Temperature 0.1 (low, deterministic)
- ✅ Explicit "JSON only" instructions in prompt
- ✅ Format examples in prompt
- ✅ Markdown fence stripping (post-processing)
- ✅ json_repair library (post-processing)
- ✅ Bracket-counting JSON extraction (post-processing)
- ✅ Flexible key name mapping (post-processing)
- ❌ None of the post-processing helps when the model outputs natural language instead of JSON

## What Works

- ✅ 3-file batches: 100% success rate, clean JSON, correct classifications
- ✅ The model's classification logic is excellent when it outputs JSON

## What Doesn't Work

- ❌ 20-file batches: ~0% success rate, model outputs explanations/refusals
- ❌ Post-processing can't fix natural language output

## Request

Please research and provide:
1. Known issues with gemma4-e4b JSON output compliance
2. Optimal prompt format for forcing JSON-only output
3. Ollama-specific parameters or features for structured output
4. Recommended batch size for reliable JSON output
5. Any gemma4-specific prompt engineering techniques
6. Whether the chat API vs generate API makes a difference for JSON compliance