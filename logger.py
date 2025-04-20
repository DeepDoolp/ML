import pandas as pd
from datetime import datetime
import os

def log_prediction(log_row, log_path="model_predictions_log.csv"):
    now = datetime.utcnow().isoformat()
    log_row["timestamp"] = now
    log_row["verified"] = False  # отметка, что не проверено
    if os.path.exists(log_path):
        pd.DataFrame([log_row]).to_csv(log_path, mode="a", index=False, header=False)
    else:
        pd.DataFrame([log_row]).to_csv(log_path, index=False)
