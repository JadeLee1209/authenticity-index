"""Thin LLM layer: Claude with forced tool use (schema-valid JSON), disk cache, parallelism.

Why forced tool use?  Asking the model to "return JSON" fails a few percent of the time at scale
(prose preambles, truncated braces). Forcing a tool call makes the API return arguments that
conform to a JSON schema, so every row in the dataset has the same structure.

Why a disk cache?  Every call is keyed by (model, prompts, schema). Re-running the pipeline after a
crash or after editing an unrelated stage costs nothing, and the cache doubles as an audit trail
of exactly what the model was asked and answered.

Backends (env LLM_BACKEND):
  anthropic  real Claude API (needs ANTHROPIC_API_KEY)                         [default]
  mock       deterministic keyword-based stand-in supplied by each caller; used by the
             offline test in tests/ and as a transparent dictionary baseline.

Models (env): LLM_MODEL for bulk coding (default claude-haiku-5-5),
              LLM_MODEL_STRONG for low-volume synthesis (default claude-sonnet-5-5).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .config import interim_dir

BACKEND = os.environ.get("LLM_BACKEND", "anthropic")
MODEL = os.environ.get("LLM_MODEL", "claude-haiku-5-5")
MODEL_STRONG = os.environ.get("LLM_MODEL_STRONG", "claude-sonnet-5-5")
MAX_WORKERS = int(os.environ.get("LLM_WORKERS", "6"))


class LLM:
    def __init__(self, model: str | None = None, backend: str | None = None,
                 cache_name: str = "llm_cache"):
        self.model = model or MODEL
        self.backend = backend or BACKEND
        self.cache_dir = interim_dir(cache_name)
        self.usage_log = interim_dir() / "llm_usage.jsonl"
        self._lock = threading.Lock()
        self._client = None
        if self.backend == "anthropic":
            import anthropic  # imported lazily so the mock path needs no SDK
            self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    # ------------------------------------------------------------------ core call
    def call_tool(self, *, system: str, user: str, tool_name: str, tool_description: str,
                  schema: dict, mock: Callable[[], dict] | None = None,
                  max_tokens: int = 2048, temperature: float = 0.0,
                  cache_tag: str = "") -> dict:
        """Return the tool-call arguments as a dict (schema-shaped)."""
        key = hashlib.sha256(json.dumps(
            [self.backend, self.model, system, user, tool_name, schema, temperature, cache_tag],
            sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / key[:2] / f"{key}.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))["output"]
            except (json.JSONDecodeError, KeyError, OSError):
                pass  # unreadable cache entry -> recompute

        if self.backend == "mock":
            if mock is None:
                raise RuntimeError("mock backend requires a mock() callable")
            out = mock()
        else:
            out = self._call_anthropic(system, user, tool_name, tool_description, schema,
                                       max_tokens, temperature)
        path.parent.mkdir(exist_ok=True)
        # Atomic write: parallel workers may compute the same key; a reader must never see a
        # half-written file.
        tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps({"model": self.model, "tool": tool_name, "system": system,
                                   "user": user, "output": out}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        return out

    def _build_request(self, system, user, tool, max_tokens, temperature) -> dict:
        """Assemble a request according to the compatibility flags learned so far."""
        f = self._flags
        req = dict(model=self.model, max_tokens=max_tokens, tools=[tool])
        if f["auto_tool"]:
            # Some models reject a forced tool choice; let the model choose, and ask it in words.
            req["tool_choice"] = {"type": "auto"}
            user = (f"{user}\n\nRespond ONLY by calling the `{tool['name']}` tool "
                    f"with every required field filled in.")
        else:
            req["tool_choice"] = {"type": "tool", "name": tool["name"]}
        req["messages"] = [{"role": "user", "content": user}]
        req["system"] = system if f["plain_system"] else \
            [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        if not f["no_temperature"]:
            req["temperature"] = temperature
        return req

    def _learn_from_error(self, e: Exception) -> bool:
        """Flip the compatibility flag the error points at. False if nothing left to try."""
        msg, f = str(e).lower(), self._flags
        for key, words in (("no_temperature", ("temperature",)),
                           ("auto_tool", ("tool_choice",)),
                           ("plain_system", ("cache_control", "system"))):
            if not f[key] and any(w in msg for w in words):
                f[key] = True
                return True
        for key in ("no_temperature", "plain_system", "auto_tool"):  # unknown cause: simplify
            if not f[key]:
                f[key] = True
                return True
        return False

    def _call_anthropic(self, system, user, tool_name, tool_description, schema,
                        max_tokens, temperature) -> dict:
        import anthropic
        tool = {"name": tool_name, "description": tool_description, "input_schema": schema}
        if not hasattr(self, "_flags"):
            self._flags = {"no_temperature": False, "auto_tool": False, "plain_system": False}
        retryable = tuple(c for c in (getattr(anthropic, n, None) for n in
                                      ("RateLimitError", "APIConnectionError", "InternalServerError",
                                       "APITimeoutError", "OverloadedError")) if isinstance(c, type))
        bad_request = getattr(anthropic, "BadRequestError", ())
        last, no_tool = None, 0
        for attempt in range(10):
            sent_flags = dict(self._flags)
            req = self._build_request(system, user, tool, max_tokens, temperature)
            try:
                resp = self._client.messages.create(**req)
            except (bad_request, TypeError) as e:
                # BadRequestError: the API rejected an optional feature for this model.
                # TypeError: this SDK version does not accept the keyword (newer SDKs dropped
                # `temperature`). Either way, learn the flag and retry with a plainer request.
                if isinstance(e, TypeError) and "keyword argument" not in str(e):
                    raise
                last = e
                with self._lock:
                    # Another thread may already have learned the fix while this request was in
                    # flight; then just retry with the current flags instead of flipping more.
                    learned = self._flags != sent_flags or self._learn_from_error(e)
                if learned:
                    continue
                raise
            except retryable as e:
                time.sleep(min(60, 2 ** attempt * 3))
                last = e
                continue
            with self._lock, open(self.usage_log, "a", encoding="utf-8") as f:
                u = resp.usage
                f.write(json.dumps({"model": self.model, "tool": tool_name,
                                    "in": u.input_tokens, "out": u.output_tokens}) + "\n")
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use":
                    inp = block.input
                    if hasattr(inp, "model_dump"):
                        inp = inp.model_dump()
                    if isinstance(inp, str):
                        inp = json.loads(inp)
                    return json.loads(json.dumps(inp, default=str))  # plain, cacheable dict
            # Auto tool choice: the model may answer in text; accept a JSON object if present.
            text = "".join(getattr(b, "text", "") for b in resp.content)
            i, j = text.find("{"), text.rfind("}")
            if i >= 0 and j > i:
                try:
                    return json.loads(text[i:j + 1])
                except json.JSONDecodeError:
                    pass
            last = RuntimeError(f"no tool call in response (stop_reason="
                                f"{getattr(resp, 'stop_reason', '?')})")
            no_tool += 1
            if no_tool >= 2:  # do not keep paying for answers in the wrong format
                break
            continue  # ask once more
        raise RuntimeError(f"LLM call failed after retries: {type(last).__name__}: {last}")


def parallel_map(fn: Callable, items: list, workers: int = MAX_WORKERS, desc: str = "") -> list:
    """Run fn over items with a thread pool, preserving order; prints coarse progress.
    Exceptions are captured per item (returned as {'_error': ...}) so one bad call never
    kills a 450-document run."""
    results = [None] * len(items)
    done = n_err = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                results[i] = fut.result()
            except Exception as e:  # noqa: BLE001 - deliberately broad, logged in output
                results[i] = {"_error": f"{type(e).__name__}: {e}"}
                n_err += 1
                if n_err == 1:  # show the first failure immediately instead of failing silently
                    print(f"  [{desc}] FIRST ERROR: {results[i]['_error'][:500]}", flush=True)
                if n_err >= 10 and n_err == done + 1:
                    # Every call so far has failed: almost certainly a configuration problem
                    # (key, credit, model name). Stop instead of burning time on the rest.
                    ex.shutdown(wait=False, cancel_futures=True)
                    raise SystemExit(f"\nABORTED: the first {n_err} {desc} calls all failed.\n"
                                     f"Error: {results[i]['_error'][:800]}")
            done += 1
            if done % 25 == 0 or done == len(items):
                print(f"  [{desc}] {done}/{len(items)}" + (f" ({n_err} errors)" if n_err else ""),
                      flush=True)
    return results
