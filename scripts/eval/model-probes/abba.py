import json, urllib.request, statistics
CHAT = "http://127.0.0.1:11434/api/chat"
PS   = "http://127.0.0.1:11434/api/ps"
SYS = ("You are a friendly tutor for a Class 6 student studying General Science. "
       "Keep answers under 80 words. Use simple language and a concrete example. Plain prose only.")
Q = "Explain in about 80 words how a shadow is formed, and give one everyday example."

def run(model, keep):
    body = json.dumps({"model": model, "stream": False, "keep_alive": keep,
        "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": Q}],
        "options": {"temperature": 0.3, "num_ctx": 4096, "num_predict": 120, "seed": 7}}).encode()
    req = urllib.request.Request(CHAT, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.load(r)
    return (d["prompt_eval_duration"]/1e6/d["prompt_eval_count"],
            d["eval_count"]/(d["eval_duration"]/1e9))

res = {}
for m in ["gemma2:2b", "gemma3n:e2b", "gemma3n:e2b", "gemma2:2b"]:   # ABBA
    pf, dec = run(m, 0)
    res.setdefault(m, []).append((pf, dec))
    print(f"  {m:14s} prefill {pf:6.1f} ms/tok   decode {dec:5.2f} tok/s")

print()
for m, v in res.items():
    print(f"{m:14s} mean prefill {statistics.mean(p for p,_ in v):6.1f} ms/tok   "
          f"mean decode {statistics.mean(d for _,d in v):5.2f} tok/s")

# resident size, model held in memory
run("gemma3n:e2b", "60s")
with urllib.request.urlopen(PS, timeout=30) as r:
    for m in json.load(r)["models"]:
        if "gemma3n" in m["name"]:
            print(f"\nollama ps: {m['name']}  resident {m['size']/2**30:.2f} GiB  "
                  f"ctx {m.get('context_length')}")
