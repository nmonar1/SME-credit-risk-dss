# SME Credit Risk Decision Support System

An explainable decision support system for SME credit risk assessment, built with a Random Forest classifier and SHAP explanations.

## What it does

Combines a Random Forest classifier trained on US SBA loan data with SHAP explanations to give loan officers a transparent SME credit risk tool. Users submit loan applications, receive a risk band (Low / Moderate / Elevated) with a calibrated probability, and see a plain-English explanation of what drove the score.

## Tech stack

- **Python 3.12**
- **scikit-learn** — Random Forest classifier + Logistic Regression baseline
- **imbalanced-learn** — SMOTENC for class balancing
- **SHAP** — per-prediction explanations
- **Streamlit** — web interface
- **SQLite** — data storage
- **bcrypt** — password hashing

## Quick start

```bash
git clone https://github.com/nmonar1/SME-credit-risk-dss.git
cd SME-credit-risk-dss
python -m venv venv
venv\Scripts\activate                 # Windows
pip install -r requirements.txt
streamlit run src/app.py

The data/ and models/ folders are not included (too large). See src/ scripts to regenerate them.

Project structure
src/          Source code (models, screens, database)
notebooks/    Exploratory data analysis
data/         Raw + processed data (gitignored)
models/       Trained models (gitignored)
database/     SQLite database (gitignored)


Status
Prototype — final build in progress.

Model
4 features: number of employees, loan amount, new vs established business, industry sector.

ROC-AUC: 0.684 · Recall: 0.678 · Precision: 0.302