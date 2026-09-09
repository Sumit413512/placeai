# PlaceAI Report Export Security

Institution report exports may contain student-, recruiter-, company-, or institution-controlled text. Spreadsheet applications can interpret cells beginning with formula markers as executable formulas.

PlaceAI therefore neutralizes risky text in CSV and XLSX exports before serialization. Strings whose first meaningful character is `=`, `+`, `-`, or `@`, and strings beginning with tab, carriage return, or line feed, are prefixed with an apostrophe so spreadsheet software treats the value as literal text. Numeric values remain numeric. PDF exports are not transformed because they are not spreadsheet-executable.

The active safe export route is `/enterprise/reports/{kind}.{fmt}` and supports CSV, XLSX, and PDF. The legacy unsanitized report route is removed from the registered enterprise router in `app/app.py` before the safe exporter is included.

Regression coverage is in `tests/test_report_export_security.py` and validates CSV escaping, XLSX cell types, numeric preservation, and PDF availability.
