import json, urllib.request
H = "http://127.0.0.1:11434/api/chat"
SYS = ("You are a friendly tutor for a Class 6 student studying General Science. "
       "Keep answers under 80 words. Use simple language and a concrete example. Plain prose only.")
Q = "Explain in about 80 words how a shadow is formed, and give one everyday example."

def run(model):
    body = json.dumps({"model": model, "stream": False, "keep_alive": 0,
        "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": Q}],
        "options": {"temperature": 0.3, "num_ctx": 4096, "num_predict": 120, "seed": 7}}).encode()
    req = urllib.request.Request(H, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.load(r)
    pf = d["prompt_eval_duration"] / 1e6 / d["prompt_eval_count"]
    dec = d["eval_count"] / (d["eval_duration"] / 1e9)
    return pf, dec, d["prompt_eval_count"], d["eval_count"]

rows = []
for m in ["gemma3:4b", "gemma3:1b", "gemma2:2b", "qwen2.5:1.5b"]:
    pf, dec, pt, ct = run(m)
    if m == "qwen2.5:1.5b": globals()["anchor"] = (pf, dec)
    rows.append((m, pf, dec, pt, ct))

for m, pf, dec, pt, ct in rows:
    print(f"{m:15s} prefill {pf:6.1f} ms/tok ({pf/anchor[0]:.2f}x)   "
          f"decode {dec:5.1f} tok/s ({dec/anchor[1]:.2f}x)   [{pt} in / {ct} out]")
