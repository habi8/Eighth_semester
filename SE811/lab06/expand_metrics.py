"""
Task 4: Expanding the Metrics
Adds to dataset.csv:
  Product:  Halstead_Volume, Halstead_Difficulty, Halstead_Effort, Comment_Density
  CK (OO):  WMC, CBO, LCOM
  Process:  Code_Churn, File_Age_Days, Fix_History

Caveats (regex-based, not a real Java parser/AST):
- Treats each file as one "class" (WMC/CBO/LCOM are file-level, not per-inner-class).
- Method/field extraction via brace-matching + regex - works for typical Java,
  can misparse unusual formatting (e.g. lambdas, anonymous inner classes with braces).
- CBO counts distinct capitalized type names referenced (imports + `new X` + `X.staticCall`),
  a proxy for real coupling analysis.
- Process metrics are computed "as of just before this commit" (historical state),
  matching the spec's "leading up to this commit" wording.

Run from the same directory as Task 1 - needs dataset.csv AND the local repo clone.
"""

import re
import math
from collections import defaultdict

import pandas as pd
from pydriller import Repository

INPUT_CSV = "dataset.csv"
OUTPUT_CSV = "extended_dataset.csv"
REPO_PATH = "./commons-csv"  # same local clone used in Task 1

JIRA_REGEX = re.compile(r"CSV-\d+", re.IGNORECASE)
BUG_KEYWORDS = re.compile(r"\b(fix|bug|issue|error|defect|patch)\b", re.IGNORECASE)


def is_bug_fix(msg):
    return bool(BUG_KEYWORDS.search(msg) or JIRA_REGEX.search(msg))


# ---------------------------------------------------------------------------
# A. Product metrics - Halstead + comment density
# ---------------------------------------------------------------------------

JAVA_KEYWORDS = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
    "class", "const", "continue", "default", "do", "double", "else", "enum",
    "extends", "final", "finally", "float", "for", "goto", "if", "implements",
    "import", "instanceof", "int", "interface", "long", "native", "new",
    "package", "private", "protected", "public", "return", "short", "static",
    "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
    "transient", "try", "void", "volatile", "while", "true", "false", "null",
}

TOKEN_PATTERN = re.compile(
    r'"(?:\\.|[^"\\])*"'          # string literal
    r"|'(?:\\.|[^'\\])*'"        # char literal
    r"|\d+\.\d+[fFdD]?"          # float literal
    r"|\d+[lLfFdD]?"             # int literal
    r"|[A-Za-z_$][A-Za-z0-9_$]*"  # identifier / keyword
    r"|>>>=|<<=|>>=|==|!=|<=|>=|&&|\|\||\+\+|--|->|::|\+=|-=|\*=|/=|%=|&=|\|=|\^=|<<|>>>|>>"
    r"|[-+*/%=<>!&|^~?:.,;(){}\[\]]"
)


def strip_comments(source):
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    source = re.sub(r"//.*", "", source)
    return source


def halstead_metrics(source):
    src = strip_comments(source or "")
    tokens = TOKEN_PATTERN.findall(src)

    operators, operands = [], []
    for tok in tokens:
        first = tok[0]
        if first in ("\"", "'") or first.isdigit():
            operands.append(tok)
        elif first.isalpha() or first in "_$":
            (operators if tok in JAVA_KEYWORDS else operands).append(tok)
        else:
            operators.append(tok)

    n1, n2 = len(set(operators)), len(set(operands))
    N1, N2 = len(operators), len(operands)
    vocab, length = n1 + n2, N1 + N2

    volume = length * math.log2(vocab) if vocab > 0 else 0.0
    difficulty = (n1 / 2) * (N2 / n2) if n2 > 0 else 0.0
    effort = difficulty * volume
    return volume, difficulty, effort


def loc(source):
    if not source:
        return 0
    return len([l for l in source.splitlines() if l.strip() != ""])


def comment_density(source):
    total = loc(source)
    if total == 0:
        return 0.0
    comment_lines = len(re.findall(r"^\s*(//|/\*|\*)", source or "", re.MULTILINE))
    return comment_lines / total


# ---------------------------------------------------------------------------
# B. CK (object-oriented) metrics - WMC, CBO, LCOM
# ---------------------------------------------------------------------------

DECISION_PATTERN = re.compile(r"\b(if|else if|for|while|case|catch|do)\b|\&\&|\|\||\?")


def cyclomatic_complexity(source):
    if not source:
        return 1
    return 1 + len(DECISION_PATTERN.findall(source))


METHOD_SIG_PATTERN = re.compile(
    r"(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?"
    r"(?:<[^>]+>\s*)?[\w<>\[\], .]+?\s+(\w+)\s*\([^)]*\)\s*"
    r"(?:throws\s+[\w.,\s]+)?\s*\{"
)


def extract_methods(source):
    """Return [(name, body_including_braces), ...] via brace matching."""
    methods = []
    for m in METHOD_SIG_PATTERN.finditer(source):
        start = m.end() - 1  # index of the opening '{'
        depth = 0
        end = start
        for i in range(start, len(source)):
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        methods.append((m.group(1), source[start:end + 1]))
    return methods


FIELD_PATTERN = re.compile(
    r"^\s*(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?"
    r"[\w<>\[\], .]+?\s+([a-zA-Z_]\w*)\s*(?:=[^;]*)?;",
    re.MULTILINE,
)


def extract_fields(source):
    return set(FIELD_PATTERN.findall(source))


def wmc(source, methods):
    if not methods:
        return cyclomatic_complexity(source)  # fallback if no methods matched
    return sum(cyclomatic_complexity(body) for _, body in methods)


COMMON_TYPES = {
    "String", "Object", "System", "Override", "Exception", "RuntimeException",
    "Integer", "Long", "Double", "Float", "Boolean", "Character", "Math",
}


def cbo(source):
    imports = re.findall(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", source, re.MULTILINE)
    imported = {i.split(".")[-1] for i in imports if not i.endswith("*")}
    used_new = re.findall(r"\bnew\s+([A-Z]\w*)", source)
    used_static = re.findall(r"\b([A-Z]\w*)\.[a-zA-Z]", source)
    referenced = (imported | set(used_new) | set(used_static)) - COMMON_TYPES
    return len(referenced)


def lcom(fields, methods):
    if not fields or len(methods) < 2:
        return 0
    method_field_use = []
    for _, body in methods:
        used = {f for f in fields if re.search(r"\b" + re.escape(f) + r"\b", body)}
        method_field_use.append(used)

    p = q = 0
    n = len(method_field_use)
    for i in range(n):
        for j in range(i + 1, n):
            if method_field_use[i] & method_field_use[j]:
                q += 1
            else:
                p += 1
    return max(0, p - q)


def ck_metrics(source):
    if not source:
        return 0, 0, 0
    methods = extract_methods(source)
    fields = extract_fields(source)
    return wmc(source, methods), cbo(source), lcom(fields, methods)


# ---------------------------------------------------------------------------
# C. Process metrics - code churn, file age, fix history (mined from git log)
# ---------------------------------------------------------------------------

def mine_process_metrics(repo_path, dataset_df):
    lookup = defaultdict(list)
    for idx, row in dataset_df.iterrows():
        lookup[(row["Commit_ID"], row["File_Name"])].append(idx)

    first_seen = {}
    churn = defaultdict(int)
    fix_count = defaultdict(int)
    process_data = {}

    for commit in Repository(repo_path).traverse_commits():
        fix = is_bug_fix(commit.msg)
        cdate = commit.committer_date

        for mod in commit.modified_files:
            path = mod.new_path or mod.old_path
            if path is None or not path.endswith(".java"):
                continue

            if path not in first_seen:
                first_seen[path] = cdate

            key = (commit.hash, path)
            if key in lookup:
                age_days = (cdate - first_seen[path]).days
                for idx in lookup[key]:
                    process_data[idx] = {
                        "Code_Churn": churn[path],
                        "File_Age_Days": age_days,
                        "Fix_History": fix_count[path],
                    }

            # update AFTER recording, so current commit's own change isn't
            # counted in "history leading up to this commit"
            churn[path] += (mod.added_lines or 0) + (mod.deleted_lines or 0)
            if fix:
                fix_count[path] += 1

    return process_data


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    df = pd.read_csv(INPUT_CSV).dropna(subset=["Source_Code"]).reset_index(drop=True)
    print(f"Loaded {len(df)} rows")

    # A + B: per-row product/CK metrics from source text
    halstead = df["Source_Code"].apply(halstead_metrics)
    df["Halstead_Volume"] = halstead.apply(lambda t: t[0])
    df["Halstead_Difficulty"] = halstead.apply(lambda t: t[1])
    df["Halstead_Effort"] = halstead.apply(lambda t: t[2])
    df["Comment_Density"] = df["Source_Code"].apply(comment_density)

    ck = df["Source_Code"].apply(ck_metrics)
    df["WMC"] = ck.apply(lambda t: t[0])
    df["CBO"] = ck.apply(lambda t: t[1])
    df["LCOM"] = ck.apply(lambda t: t[2])
    print("Computed Halstead + CK metrics")

    # C: process metrics via a second pass over commit history
    process_data = mine_process_metrics(REPO_PATH, df)
    df["Code_Churn"] = df.index.map(lambda i: process_data.get(i, {}).get("Code_Churn", 0))
    df["File_Age_Days"] = df.index.map(lambda i: process_data.get(i, {}).get("File_Age_Days", 0))
    df["Fix_History"] = df.index.map(lambda i: process_data.get(i, {}).get("Fix_History", 0))
    matched = sum(1 for i in df.index if i in process_data)
    print(f"Matched process metrics for {matched}/{len(df)} rows")

    df.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved -> {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
