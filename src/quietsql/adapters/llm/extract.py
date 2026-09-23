import re

FENCE = re.compile(r"```(?:sql)?", re.IGNORECASE)
LEADING_SELECT = re.compile(r"^\s*SELECT\s+(?=(SELECT|WITH)\b)", re.IGNORECASE)


def extract_sql(raw: str) -> str:
    text = raw.strip()
    if "```" in text:
        parts = FENCE.split(text)
        candidates = [
            p.strip() for p in parts if re.match(r"^\s*(select|with)\b", p, re.IGNORECASE)
        ]
        text = candidates[0] if candidates else parts[0].strip()
    text = text.split(";")[0].strip()
    text = LEADING_SELECT.sub("", text)
    lines = []
    for line in text.splitlines():
        if lines and re.match(r"^[A-Z][a-z].*\.$", line.strip()):
            break
        lines.append(line)
    return "\n".join(lines).strip()
