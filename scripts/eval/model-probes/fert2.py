import json, urllib.request, sys
H = "http://127.0.0.1:11434/api/generate"
HI = ("छाया तब बनती है जब कोई अपारदर्शी वस्तु प्रकाश के मार्ग में आ जाती है। "
      "छाया सदैव वस्तु के उस ओर बनती है जो प्रकाश स्रोत से दूर होती है। "
      "पारदर्शी वस्तुएँ प्रकाश को अपने भीतर से जाने देती हैं, इसलिए वे गहरी छाया नहीं बनातीं। "
      "जब वस्तु और स्रोत के बीच की दूरी बदलती है तब छाया का आकार भी बदल जाता है।")
MR = ("जेव्हा एखादी अपारदर्शक वस्तू प्रकाशाच्या मार्गात येते तेव्हा सावली तयार होते. "
      "सावली नेहमी वस्तूच्या त्या बाजूला तयार होते जी प्रकाश स्रोतापासून दूर असते. "
      "पारदर्शक वस्तू प्रकाशाला आरपार जाऊ देतात, म्हणून त्या गडद सावली तयार करत नाहीत. "
      "वस्तू आणि स्रोत यांच्यातील अंतर बदलले की सावलीचा आकारही बदलतो.")
EN = ("A shadow is formed when an opaque object comes in the path of light. "
      "The shadow is always formed on the side of the object away from the light source. "
      "Transparent objects allow light to pass through them, so they do not form dark shadows. "
      "The size of a shadow changes when the distance between the object and the source changes.")
def count(model, text):
    b = json.dumps({"model": model, "prompt": text, "raw": True, "stream": False,
                    "keep_alive": 0, "options": {"num_predict": 1}}).encode()
    with urllib.request.urlopen(urllib.request.Request(H, b, {"Content-Type":"application/json"}), timeout=600) as r:
        return json.load(r)["prompt_eval_count"]
for model in sys.argv[1:]:
    base = count(model, "x")
    out = []
    for name, t in (("En", EN), ("Hi", HI), ("Mr", MR)):
        n = count(model, t) - (base - 1)
        out.append(f"{name} {n/len(t)*1000:5.1f}")
    print(f"{model:26s} tok/1k chars:  " + "   ".join(out))
