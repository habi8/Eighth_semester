"""
Task 1: Mining Software Repositories
Mine apache/commons-csv for bug-fixing vs clean commits.
Output: dataset.csv with columns Commit_ID, Commit_Date, File_Name, Source_Code, Label
"""

import csv
import random
import re
from pydriller import Repository

REPO_PATH = "./commons-csv"  # local clone path, see clone command below
OUTPUT_CSV = "dataset.csv"

# Jira ticket pattern for this project (e.g. CSV-123)
JIRA_REGEX = re.compile(r"CSV-\d+", re.IGNORECASE)
BUG_KEYWORDS = re.compile(r"\b(fix|bug|issue|error|defect|patch)\b", re.IGNORECASE)

# Mine all .java files - src/main AND src/test
def is_source_file(path):
    return path is not None and path.endswith(".java")

def is_bug_fix(commit_msg):
    return bool(BUG_KEYWORDS.search(commit_msg) or JIRA_REGEX.search(commit_msg))

def main():
    defective_rows = []   # Label 1
    clean_candidates = [] # pool to sample Label 0 from

    for commit in Repository(REPO_PATH).traverse_commits():
        msg = commit.msg
        bug_fix = is_bug_fix(msg)

        for mod in commit.modified_files:
            if not is_source_file(mod.new_path or mod.old_path):
                continue

            if bug_fix:
                # source_code_before = state of file BEFORE the fix was applied
                if mod.source_code_before:
                    defective_rows.append({
                        "Commit_ID": commit.hash,
                        "Commit_Date": commit.committer_date.isoformat(),
                        "File_Name": mod.new_path or mod.old_path,
                        "Source_Code": mod.source_code_before,
                        "Label": 1,
                    })
            else:
                # candidate for clean set - use current version of the file at this commit
                if mod.source_code:
                    clean_candidates.append({
                        "Commit_ID": commit.hash,
                        "Commit_Date": commit.committer_date.isoformat(),
                        "File_Name": mod.new_path or mod.old_path,
                        "Source_Code": mod.source_code,
                        "Label": 0,
                    })

    print(f"Defective (Label 1): {len(defective_rows)}")
    print(f"Clean candidates pool: {len(clean_candidates)}")

    # Sample clean commits to roughly balance dataset (adjust ratio as needed)
    n_clean = min(len(clean_candidates), len(defective_rows))
    random.seed(42)
    clean_rows = random.sample(clean_candidates, n_clean) if n_clean > 0 else []

    all_rows = defective_rows + clean_rows
    random.shuffle(all_rows)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Commit_ID", "Commit_Date", "File_Name", "Source_Code", "Label"])
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Saved {len(all_rows)} rows -> {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
