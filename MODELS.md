# Models

Every model call, in the product and in the tools we used to build it, goes to
the ASU Research Computing gateway. No OpenAI, no Anthropic, nothing off campus.

**Endpoint:** `https://openai.rc.asu.edu/v1` (OpenAI-compatible)
**Auth:** `Authorization: Bearer $RC_LLM_API_KEY`, read from `.env`
**Keys:** one per person from [voyager.rc.asu.edu](https://voyager.rc.asu.edu),
never committed

All IDs below were read from the gateway's own `/v1/models` listing on
3 September 2026, not guessed.

## In the product

Two models do the work. That is the whole list.

| ID | Role | Calls |
|---|---|---|
| `qwen3-vl-32b-instruct` | Describes each picture | one per picture |
| `gemma4-31b-it` | Summarises the file once, to give each picture some background | one per file |

Both are set in [`slidesight/config.py`](slidesight/config.py) as `MODEL_VISION`
and `MODEL_TEXT`.

`qwen3-vl-32b-instruct` is the vision-capable option on the gateway. It takes
base64 data URLs and returns the description, a decorative flag, a confidence
score and a reason in a single reply. Confirmed working end to end on a real
lecture slide: 790 prompt tokens, 222 completion tokens, valid JSON back.

`gemma4-31b-it` is text only, and is used only for the per-file summary. It is
deliberately **not** used to check the picture descriptions. A model that cannot
see the picture cannot catch a made-up number in a description of it.

Requests are capped at 60 seconds with two retries, and no more than four run at
once. The SDK default is 600 seconds with two retries, which turns one stalled
request into a half-hour hang.

## In the coding assistant

We wrote this project with [OpenCode](https://opencode.ai), an open-source AI
coding assistant, pointed at the same gateway instead of a commercial API. The
rule is that AIR models have to run the product. They also built it.

Default: **`devstral2-123b`**.

Configured and available in the model picker, all on AIR:

| | | |
|---|---|---|
| `devstral2-123b` | `glm-5-3` | `glm-5-3-flash` |
| `kimi-k2-7-code` | `north-mini-code` | `qwen3-coder-next` |
| `qwen3-coder-30b-a3b-instruct` | `qwen35-122b-a10b` | `qwen-agentworld-35b-a3b` |
| `gpt-oss-120b` | `minimax-m2-7` | `laguna-s-2-1` |
| `muse-glimmer-30b` | | |

The config lives at `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "asu": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "ASU Air",
      "options": {
        "baseURL": "https://openai.rc.asu.edu/v1",
        "apiKey": "{env:OPENAI_API_KEY}"
      }
    }
  },
  "model": "asu/devstral2-123b"
}
```

## What we learned probing the gateway

The gateway exposes **48 models**. A coding assistant needs one that can make
real tool calls, so we sent all the plausible candidates an actual tool-call
request rather than trusting a badge. Thirteen answered with a real `tool_calls`
response; those are the thirteen above.

Two things worth knowing if you do the same:

`muse-glimmer-30b` looked like it had no tool support, because it answered a
weakly-phrased question in prose instead of calling the tool. Asking again with
`tool_choice: "required"` produced a proper tool call. It supports tools; it just
declines easily.

`minimax-m3` is listed on the gateway but broken behind it. Every request returns
HTTP 400 with `model minimax-m3-mxfp4 does not exist`. Do not build anything on
it.

The gateway itself is not always up. On the evening of 3 September the vision
model returned `503 overloaded_error` for several minutes and every request
failed. That is why the pipeline now treats "no model answered for any picture"
as a failure instead of quietly reporting a finished run with nothing written.

## Why on-campus and not a commercial API

Lecture slides are unpublished faculty work. Sending them to an outside vendor is
a policy question before it is a technical one.

Some decks carry graded student work, which cannot leave campus at all.

The volume is real. Hundreds of pictures per file, across thousands of files.
That is a bill anywhere else.

AIR keeps everything on ASU hardware and does not train on what passes through.
