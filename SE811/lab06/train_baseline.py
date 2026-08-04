"""
Task 2: Traditional Machine Learning for Defect Prediction
Reads dataset.csv from Task 1, computes handcrafted metrics on Java source,
trains baseline classifiers, prints classification reports.
"""

import re
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.naive_bayes import GaussianNB
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report

INPUT_CSV = "extended_dataset.csv"  # Task 4 output - has Halstead/CK/process cols already

# --- Metric extraction (Java source, regex-based - no external Java parser needed) ---

# Decision-point keywords/operators that each add +1 to cyclomatic complexity
DECISION_PATTERN = re.compile(
    r"\b(if|else if|for|while|case|catch|do)\b|\&\&|\|\||\?"
)

# Rough variable declaration match: TYPE name = ... ; or TYPE name ;
# Catches primitives, common collections, and generics like List<String>
VAR_DECL_PATTERN = re.compile(
    r"\b(?:int|long|short|byte|float|double|boolean|char|String|var|"
    r"List|Map|Set|ArrayList|HashMap|HashSet|Object)"
    r"(?:<[^>]*>)?\s+([a-zA-Z_]\w*)\s*[=;,)]"
)


def loc(source):
    if not source:
        return 0
    lines = [l for l in source.splitlines() if l.strip() != ""]
    return len(lines)


def cyclomatic_complexity(source):
    if not source:
        return 1
    matches = DECISION_PATTERN.findall(source)
    return 1 + len(matches)  # base complexity of 1 + one per decision point


def variable_count(source):
    if not source:
        return 0
    return len(VAR_DECL_PATTERN.findall(source))


def comment_density(source):
    if not source:
        return 0.0
    total = loc(source)
    if total == 0:
        return 0.0
    comment_lines = len(re.findall(r"^\s*(//|/\*|\*)", source, re.MULTILINE))
    return comment_lines / total


def main():
    df = pd.read_csv(INPUT_CSV)
    df = df.dropna(subset=["Source_Code"])

    print(f"Loaded {len(df)} rows")

    # Basic metrics (Task 2) - computed here since extended_dataset.csv doesn't carry these
    df["LOC"] = df["Source_Code"].apply(loc)
    df["Cyclomatic_Complexity"] = df["Source_Code"].apply(cyclomatic_complexity)
    df["Variable_Count"] = df["Source_Code"].apply(variable_count)
    df["Comment_Density"] = df["Source_Code"].apply(comment_density)

    # Task 4 columns already present in extended_dataset.csv - just reference them
    task4_cols = ["Halstead_Volume", "Halstead_Difficulty", "Halstead_Effort",
                  "WMC", "CBO", "LCOM", "Code_Churn", "File_Age_Days", "Fix_History"]
    missing = [c for c in task4_cols if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing Task 4 columns {missing} - run expand_metrics.py first")

    feature_cols = ["LOC", "Cyclomatic_Complexity", "Variable_Count", "Comment_Density"] + task4_cols
    X = df[feature_cols]
    y = df["Label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Scale features - matters for SVM and Logistic Regression, harmless for tree models
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    models = {
        "Logistic Regression": LogisticRegression(max_iter=1000),
        "Decision Tree": DecisionTreeClassifier(random_state=42),
        "Random Forest": RandomForestClassifier(random_state=42),
        "SVM": SVC(probability=True, random_state=42),
        "Naive Bayes": GaussianNB(),
    }

    for name, model in models.items():
        print(f"\n{'='*20} {name} {'='*20}")
        if name in ("Logistic Regression", "SVM"):
            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)
        else:
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
        print(classification_report(y_test, y_pred, zero_division=0))


if __name__ == "__main__":
    main()
