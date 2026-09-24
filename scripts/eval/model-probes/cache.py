"""Strict-extension KV cache reuse probe (T1 -> T2), after the design in
docs/experiments/EXP-small-model-shortlist.md step 7."""
import json, urllib.request, sys
H = "http://127.0.0.1:11434/api/chat"
SYS = ("You are a friendly tutor for a Class 6 student studying General Science. "
       "Keep answers under 80 words. Use simple language and a concrete example. Plain prose only. "
       "Use only these excerpts from the textbook: [1] An opaque object does not allow light to pass "
       "through it. When an opaque object is placed in the path of light, a shadow is formed on the "
       "screen behind it. [2] Transparent objects allow light to pass through them.")

def chat(model, msgs, keep="5m"):
    body = json.dumps({"model": model, "stream": False, "keep_alive": keep, "messages": msgs,
        "options": {"temperature": 0.3, "num_ctx": 4096, "num_predict": 80, "seed": 7}}).encode()
    req = urllib.request.Request(H, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.load(r)
    return d["message"]["content"], d["prompt_eval_duration"]/1e6, d["prompt_eval_count"]

def unload(model):
    chat(model, [{"role": "user", "content": "x"}], keep=0)

for model in sys.argv[1:]:
    unload(model)
    m1 = [{"role": "system", "content": SYS}, {"role": "user", "content": "What is a shadow?"}]
    a1, p1, n1 = chat(model, m1)
    # T2: strict extension of T1 -- the follow-up case
    m2 = m1 + [{"role": "assistant", "content": a1},
               {"role": "user", "content": "Why does its length change during the day?"}]
    _, p2_warm, n2 = chat(model, m2)
    unload(model)                      # cold reference for the same prompt
    _, p2_cold, _ = chat(model, m2)
    reuse = 1 - p2_warm / p2_cold
    print(f"{model:24s} T1 {p1:7.0f}ms/{n1}tok | T2 warm {p2_warm:7.0f}ms  cold {p2_cold:7.0f}ms "
          f"({n2} tok) -> reuse {reuse*100:5.1f}%")
    unload(model)
