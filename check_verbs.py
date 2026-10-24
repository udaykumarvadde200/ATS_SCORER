import re, sys, pdfplumber
from backend.utils.action_verbs import detect_action_verbs, ACTION_VERBS

text = "\n".join(p.extract_text() or "" for p in pdfplumber.open(sys.argv[1]).pages)
print("Detected:", detect_action_verbs(text))

firsts = set()
for line in re.sub("[\u2022\u25cf\u25aa\u25e6\uf0b7]", "\n", text).splitlines():
    m = re.match(r"[\s\-\*]*([A-Za-z]+)", line.strip())
    if m and m.group(1).lower() not in ACTION_VERBS:
        firsts.add(m.group(1))
print("Line-starting words NOT in the verb list:", sorted(firsts))
