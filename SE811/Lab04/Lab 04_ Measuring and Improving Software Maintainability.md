# Measuring and Improving Software Maintainability 

You are handed a system that works perfectly and passes its basic functional tests. Your job is to measure its current maintainability, identify the worst-offending areas, refactor the code, and prove that your changes made the codebase easier to maintain.

# Lab Setup & Prerequisites

# You will need a terminal environment with Python 3.x installed. Before starting, open your terminal and install the required static analysis tools using pip:

# pip install radon

## Step A: Download & Measure the Baseline

1. Download the attached files   
2. Without changing anything, run the following commands in your terminal to analyze the messy code:  
   * **To calculate Cyclomatic Complexity:** radon cc file\_name.py \-s  
   * **To calculate Maintainability Index:** radon mi file\_name.py  
3. Take screenshots or note down these initial baseline numbers and letter grades for your report.

## Step B: Code Review

Open the files in your code editor. Analyze the functions that scored lower grades. Identify the problematic area.

## Step C: Refactor the Code

Rewrite and modularize the code into a new file named clean\_file\_name.py. Your refactored version must output the exact same results as the legacy version, but use clean coding practices:

## Step D: Verify Improvements

Run the radon commands again, this time against your new file. Your goal is to raise the **Maintainability Index.**

## Required Deliverables

Your final PDF report must include:

1. **Metrics Comparison Table:** Side-by-side comparison (Before vs. After) of Average Complexity, total Lines of Code (LOC), and the Maintainability Index score.  
2. **Problem Identification:** A brief explanation naming 2–3 reasons why the original code was poorly written.  
3. **Refactoring Explanation:** A short summary detailing the specific strategies you used to clean up the code.

**AI Tools Declaration (Mandatory):**

You need to submit a separate AI declaration PDF. You must transparently declare its usage by copying and filling out the template below:

* **AI Tools Used:**   
* **Core Purpose:**   
* **Prompts Shared:** \[Copy and paste 1–2 key prompts you used to get assistance from the AI.\]  
* **Critique & Validation:** \[Explain in 2 sentences how you verified that the code generated or suggested by the AI was accurate, met the assignment constraints, and did not introduce functional bugs.\]

