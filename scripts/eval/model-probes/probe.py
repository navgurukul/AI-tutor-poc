import json, urllib.request, sys
H = "http://127.0.0.1:11434/api/chat"

RULES = (
 "You are a friendly tutor for a Class 6 student studying General Science. "
 "Keep answers under 80 words unless asked for more. Use simple language and a concrete example. "
 "Never invent facts; if you are unsure, say so plainly. Write plain prose only: no markdown, no bullet "
 "symbols, and never use emojis. Reply in {lang}. "
 "Most important rule: explain the idea directly and clearly. "
 "Write your ENTIRE reply in {lang}, and only {lang}, using the Devanagari script. Every sentence must be "
 "in {lang}. Do not use English or any other script. Do NOT repeat a word or phrase — make each point once, then stop."
)
EXCERPT = (
 "\n\nUse only these excerpts from the textbook:\n"
 "[1] An opaque object does not allow light to pass through it. When an opaque object is placed in the path "
 "of light, a shadow is formed on the screen behind it. The shadow is formed on the side of the object away "
 "from the source of light.\n"
 "[2] Transparent objects allow light to pass through them. Translucent objects allow light to pass through "
 "them only partially, so objects seen through them are not clear.\n"
)
QUESTIONS = {"Marathi": "सावली कशी तयार होते?", "Hindi": "छाया कैसे बनती है?"}

def run(model, lang):
    body = json.dumps({
        "model": model, "stream": False, "keep_alive": 0,
        "messages": [{"role": "system", "content": RULES.format(lang=lang) + EXCERPT},
                     {"role": "user", "content": QUESTIONS[lang]}],
        "options": {"temperature": 0.3, "num_ctx": 4096, "num_predict": 200, "seed": 7},
    }).encode()
    req = urllib.request.Request(H, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.load(r)
    a = d["message"]["content"].strip()
    pt, ct = d["prompt_eval_count"], d["eval_count"]
    tps = ct / (d["eval_duration"] / 1e9)
    print(f"\n### {model} — {lang}")
    print(f"prompt {pt} tok | answer {ct} tok / {len(a)} chars | {tps:.1f} tok/s | "
          f"{ct/max(len(a),1)*1000:.0f} tok per 1k chars")
    print(a)

for m in sys.argv[1:]:
    for lang in ("Marathi", "Hindi"):
        run(m, lang)
