# MODELS.md

Every model call in SlideSight goes to the ASU Research Computing LLM gateway.
No OpenAI, no Anthropic, no external inference anywhere in the shipped product.

**Endpoint:** `https://openai.rc.asu.edu/v1` (OpenAI-compatible)
**Auth:** `Authorization: Bearer $RC_LLM_API_KEY`, loaded from `.env`
**Keys:** issued per person from [voyager.rc.asu.edu](https://voyager.rc.asu.edu). Never committed.

## Models in use

| Role | Model ID | Calls per deck | Why this one |
|---|---|---|---|
| Image description | `qwen3-vl-32b-instruct` | one per image | The vision-capable option on AIR. Takes base64 data URLs. Returns description, decorative flag, confidence, and reason in a single call. |
| Deck summary | `gemma4-31b-it` | one per deck | Text-only, cheap, gives each image prompt background context about the deck's subject and level. |

Both IDs were read from the gateway's own `/v1/models` listing, not guessed.

## Verified on the gateway

Checked 2026-09-03 against `GET /v1/models` and live calls:

- `qwen3-vl-32b-instruct` — accepts `image_url` content parts with
  `data:image/jpeg;base64,...`. Confirmed end to end on a real lecture slide:
  790 prompt tokens, 222 completion tokens, valid JSON returned.
- `gemma4-31b-it` — text only, used only for the deck summary. It is **not**
  used to critique image descriptions; a text-only model cannot see the image
  and so cannot catch a hallucinated value.

## Notes for anyone re-running this

- The gateway exposes 48 models. Of the ones we probed for tool calling, 13
  return real `tool_calls`; `muse-glimmer-30b` supports tools but often declines
  under `tool_choice:"auto"`.
- `minimax-m3` is listed but **broken server-side** — it returns HTTP 400,
  `model minimax-m3-mxfp4 does not exist`. Avoid it.
- Concurrency is capped with a semaphore (default 4). Firing every image at once
  gets rate-limited.

## Why AIR and not a commercial API

- Lecture decks are unpublished faculty intellectual property. Sending them to a
  commercial vendor is a policy problem before it is a technical one.
- A deck carrying graded student work cannot leave campus at all.
- Volume: hundreds of images per deck across thousands of decks. That is a real
  bill anywhere else.
- AIR keeps all inference on ASU hardware and does not train on the data.
