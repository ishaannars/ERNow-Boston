# Original ERNow pipeline (legacy)

The first ERNow version modeled 36 hospital-period observations across 6 Boston hospitals, comparing
Ridge regression, Random Forest, and a Persistence baseline. Persistence won, and 36 rows were too few
to learn more, so the project moved to the 4,438-hospital national panel (`national_model.py`).
These files are kept for reference. The live app does not use them.

- `cms_history_pipeline.py` builds the Boston OP-18b history from CMS archives
- `historical_modeling.py` and `modeling.py` are the original model comparisons
