Synthetic Product Dataset
=========================

Folders:
- images/: 10 PNG files (each one product) with product info and ingredients
- pdfs/:   10 PDF files (each one product) with product info and ingredients
- texts/:  10 TXT files (each one product) with product info and ingredients

CSVs:
- product_index.csv: maps product_id -> relative file path for the product
- forbidden_ingredients.csv: list of forbidden ingredients

Notes:
- Some products may contain forbidden ingredients (on purpose) to test acceptance/rejection logic.
