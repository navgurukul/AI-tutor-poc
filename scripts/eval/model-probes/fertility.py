import json, urllib.request
H = "http://127.0.0.1:11434/api/generate"

EN = ("A shadow is formed when an opaque object comes in the path of light. "
      "The shadow is always formed on the side of the object away from the light source. "
      "Transparent objects allow light to pass through them, so they do not form dark shadows. "
      "The size of a shadow changes when the distance between the object and the source changes.")
HI = ("छाया तब बनती है जब कोई अपारदर्शी वस्तु प्रकाश के मार्ग में आ जाती है। "
      "छाया सदैव वस्तु के उस ओर बनती है जो प्रकाश स्रोत से दूर होती है। "
      "पारदर्शी वस्तुएँ प्रकाश को अपने भीतर से जाने देती हैं, इसलिए वे गहरी छाया नहीं बनातीं। "
      "जब वस्तु और स्रोत के बीच की दूरी बदलती है तब छाया का आकार भी बदल जाता है।")
MR = ("जेव्हा एखादी अपारदर्शक वस्तू प्रकाशाच्या मार्गात येते तेव्हा सावली तयार होते. "
      "सावली नेहमी वस्तूच्या त्या बाजूला तयार होते जी प्रकाश स्रोतापासून दूर असते. "
      "पारदर्शक वस्तू प्रकाशाला आरपार जाऊ देतात, म्हणून त्या गडद सावली तयार करत नाहीत. "
      "वस्तू आणि स्रोत यांच्यातील अंतर बदलले की सावलीचा आकारही बदलतो.")

def count(model, text):
    body = json.dumps({"model": model, "prompt": text, "raw": True, "stream": False,
                       "keep_alive": 0, "options": {"num_predict": 1}}).encode()
    req = urllib.request.Request(H, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["prompt_eval_count"]

for model in ["qwen2.5:1.5b", "gemma2:2b", "gemma3:4b"]:
    base = count(model, "x")          # BOS + 1 token, to cancel the constant
    print(f"\n{model}  (control 'x' = {base} tokens)")
    for name, text in (("English", EN), ("Hindi", HI), ("Marathi", MR)):
        n = count(model, text) - (base - 1)
        print(f"  {name:8s} {len(text):5d} chars -> {n:5d} tokens   "
              f"{n/len(text)*1000:6.1f} tok/1k chars   {n/len(text.split()):5.2f} tok/word")
