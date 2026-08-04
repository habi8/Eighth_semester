"""
Task 3: Evaluation
Computes F1-Score, Precision, Recall, AUC-ROC for each model, prints comparison table.
Reuses same features/split logic as train_baseline.py.
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
from sklearn.metrics import (
    f1_score, precision_score, recall_score, roc_auc_score
)

INPUT_CSV = "extended_dataset.csv"  # Task 4 output - has Halstead/CK/process cols already

DECISION_PATTERN = re.compile(
    r"\b(if|else if|for|while|case|catch|do)\b|\&\&|\|\||\?"
)
VAR_DECL_PATTERN = re.compile(
    r"\b(?:int|long|short|byte|float|double|boolean|char|String|var|"
    r"List|Map|Set|ArrayList|HashMap|HashSet|Object)"
    r"(?:<[^>]*>)?\s+([a-zA-Z_]\w*)\s*[=;,)]"
)


def loc(source):
    if not source:
        return 0
    return len([l for l in source.splitlines() if l.strip() != ""])


def cyclomatic_complexity(source):
    if not source:
        return 1
    return 1 + len(DECISION_PATTERN.findall(source))


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
    df = pd.read_csv(INPUT_CSV).dropna(subset=["Source_Code"])

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

    results = []

    for name, model in models.items():
        needs_scaling = name in ("Logistic Regression", "SVM")
        Xtr = X_train_scaled if needs_scaling else X_train
        Xte = X_test_scaled if needs_scaling else X_test

        model.fit(Xtr, y_train)
        y_pred = model.predict(Xte)

        # AUC-ROC needs probability/score for the positive class (Label 1)
        if hasattr(model, "predict_proba"):
            y_score = model.predict_proba(Xte)[:, 1]
        else:
            y_score = model.decision_function(Xte)

        results.append({
            "Model": name,
            "Precision": precision_score(y_test, y_pred, zero_division=0),
            "Recall": recall_score(y_test, y_pred, zero_division=0),
            "F1-Score": f1_score(y_test, y_pred, zero_division=0),
            "AUC-ROC": roc_auc_score(y_test, y_score),
        })

    results_df = pd.DataFrame(results).set_index("Model").round(3)
    print("\n" + "=" * 60)
    print("MODEL COMPARISON")
    print("=" * 60)
    print(results_df.to_string())

    best_f1 = results_df["F1-Score"].idxmax()
    best_auc = results_df["AUC-ROC"].idxmax()
    print(f"\nBest F1-Score: {best_f1} ({results_df.loc[best_f1, 'F1-Score']})")
    print(f"Best AUC-ROC: {best_auc} ({results_df.loc[best_auc, 'AUC-ROC']})")

    results_df.to_csv("model_comparison.csv")
    print("\nSaved -> model_comparison.csv")


if __name__ == "__main__":
    main()
