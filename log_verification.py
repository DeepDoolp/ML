import pandas as pd
import requests
from datetime import datetime, timedelta
import time

# путь к логу
log_path = "model_predictions_log.csv"
df = pd.read_csv(log_path)

# преобразуем дату
df['timestamp'] = pd.to_datetime(df['timestamp'])

updated = 0
now = datetime.utcnow()

for idx, row in df.iterrows():
    if row.get("verified", False):
        continue  # уже проверено

    ts = row['timestamp']
    if (now - ts).total_seconds() >= 4 * 3600:  # прошло 4 часа
        # узнаем цену сейчас
        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {
                "symbol": "ETHUSDT",
                "interval": "1h",
                "limit": 1,
                "startTime": int(ts.timestamp() * 1000) + 4 * 3600 * 1000
            }
            r = requests.get(url, params=params)
            data = r.json()
            close_price = float(data[0][4])  # close

            # считаем дельту
            price_now = row['eth_price_now']
            delta = (close_price - price_now) / price_now

            # назначаем лейбл
            if delta > 0.0025:
                actual = "long"
            elif delta < -0.0025:
                actual = "short"
            else:
                actual = "neutral"

            df.at[idx, "actual_label"] = actual
            df.at[idx, "verified"] = True
            updated += 1
            time.sleep(0.1)
        except Exception as e:
            print(f"Ошибка при обновлении строки {idx}: {e}")

df.to_csv(log_path, index=False)
print(f"Обновлено {updated} строк.")
