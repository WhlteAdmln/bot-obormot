# LLM servers

The bot talks to any server that implements the OpenAI chat completions API.
Set `LLM_BASE_URL` to the base URL that ends with `/v1`.

## Required

| Endpoint | Purpose |
|----------|---------|
| `POST /v1/chat/completions` | Chat generation with streaming (`stream: true`). |

Images are sent as `image_url` content parts, so image questions need a model
that supports vision.

## Optional

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/models` | Reports the context size on many servers. |
| `GET /props` | llama.cpp extension that reports the context size. |
| `POST /tokenize` | llama.cpp extension for exact token counting. |

## Context size

The bot needs the context size to decide how much history fits in a request.
It looks for the value in this order:

1. `LLM_CONTEXT_SIZE`, when set.
2. `/props` of llama.cpp.
3. The metadata of `/v1/models`. The bot understands the fields `max_model_len`,
   `context_length`, `max_context_length` and `n_ctx`.

If none of them reports a value, set `LLM_CONTEXT_SIZE` yourself.

## Token counting

`LLM_TOKEN_COUNTING` selects how tokens are counted.

| Value | Behavior |
|-------|----------|
| `auto` | Try `/tokenize`, then fall back to an estimate. |
| `llamacpp` | Use `/tokenize` only. |
| `estimate` | Estimate from the text length. Works with every server. |

## Tested servers

| Server | Notes |
|--------|-------|
| llama.cpp (`llama-server`) | Full support: `/props` and `/tokenize` are used. |
| vLLM | Use `estimate` or `auto`. The context size comes from `max_model_len`. |
| Other OpenAI-compatible servers | Set `LLM_CONTEXT_SIZE` and use `estimate`. |

Run `bot-obormot doctor` to check that the server answers on `/models`.
