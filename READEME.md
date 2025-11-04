# 🧪 Product Safety Compliance AI Challenge

## 📋 Overview

This technical challenge evaluates a candidate’s ability to design and implement an **AI-powered system** that determines whether a **product** (represented via various unstructured and structured data sources) should be **accepted or rejected** based on the presence of **forbidden chemical ingredients**.

This task mirrors a **real-world client problem** — building a system capable of processing messy, multi-format data and making decisions using AI reasoning or NLP techniques.

Candidates are expected to build a **RESTful API** endpoint (or optionally a small UI) that performs this evaluation.

---

## 🎯 Objective

You will create an AI system that:

1. **Ingests and processes product data** from a mix of files:

   - PDFs (e.g., product labels)
   - Images (e.g., ingredient lists)
   - CSVs or text files (e.g., structured data tables)

2. **Extracts and interprets the ingredient information** from these files.
3. **Compares extracted ingredients** against a list of _forbidden ingredients_.
4. **Determines** whether each product should be **Accepted** or **Rejected**.
5. Returns results through a **REST API endpoint** or optional **UI interface**.

The system should be **robust and generalizable**, i.e., able to handle new data that wasn’t part of the provided dataset.

---

## 📁 Repository Structure

```
.
├── data/
│   ├── samples/               # Example products provided to candidates (20)
│   ├── evaluation/            # Held-out test products (not shared)
│   ├── forbidden_ingredients.csv
│   └── README_data.md         # Notes about simulated data and formats
└── README.md                  # This file
```

---

## 🧠 Challenge Requirements

### Functional Requirements

- Build an API (e.g., `/evaluate_product`) that:

  - Accepts input files or file paths.
  - Returns a JSON response indicating:

    ```json
    {
      "product_name": "Example Product",
      "status": "Rejected",
      "reason": ["Contains Glucose", "Contains Sodium Benzoate"]
    }
    ```

- Must handle **unstructured data** (e.g., OCR from images, PDF text extraction).
- Must detect variations in **ingredient naming conventions** (e.g., “Glucose” vs. “D-Glucopyranose”).
- Must allow **custom forbidden ingredient lists** (not hardcoded).

### Technical Requirements

- The solution may use **any AI/NLP tools or LLMs**.
- Must include:

  - Clear **documentation** and **code comments**.
  - A simple **setup guide** (requirements.txt, package.json Dockerfile, or equivalent).
  - A **Loom video (5–10 mins)** explaining the approach, thought process, and architecture.

---

## 🕒 Time Expectation

- Expected effort: **~5 hours**.
- The challenge is intentionally open-ended — efficiency, clarity, and design choices will be evaluated as much as the final output.

---

## 📦 Submission Instructions

1. **Fork** this repository (you’ll receive access once selected for the challenge).
2. Create a new branch named after yourself (e.g., `feature/jane-doe-solution`).
3. Implement your solution within your branch.
4. Submit a **Pull Request (PR)** to that fork when finished.
5. Include in your PR description:

   - Loom video link
   - Setup/Run instructions
   - Any assumptions made

6. Share the private fork and email the branch link to the recruiting team.

---

## 🧪 Evaluation Criteria

| Area                | Description                                                     |
| ------------------- | --------------------------------------------------------------- |
| **Data Handling**   | Ability to parse and extract information from unstructured data |
| **AI/ML Reasoning** | Creativity and correctness of AI/NLP solution                   |
| **Code Quality**    | Structure, readability, and maintainability                     |
| **System Design**   | Logical architecture, generalization, modularity                |
| **Presentation**    | Clarity and professionalism of Loom walkthrough                 |
| **Completeness**    | Meets submission and documentation requirements                 |

---

## 🧩 Example Workflow

1. Load all product files from `/data/samples/`.
2. Extract text (via PDF parser or OCR).
3. Match ingredients against `forbidden_ingredients.csv`.
4. Return JSON decision for each product.
5. (Optional) Build a small web UI to process or visualize the results.

---

## 🔐 Notes

- Half of the dataset (evaluation set) will not be shared — your system must generalize.
- Do **not** hardcode answers or ingredient lists.
- You are free to use **TypeScript or Python** with reasonable setup reproducibility.

---

## 💬 Contact & Support

For technical questions about this challenge, reach out to your contact at Brainforge!
Do **not** open public GitHub issues or discussions about the challenge.
