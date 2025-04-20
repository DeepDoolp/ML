import streamlit as st
import pandas as pd
import os

def run():
    st.header("✅ Оценка модели")
    
    if not os.path.exists("model_predictions_log.csv"):
        st.warning("Лог с предсказаниями пока пуст.")
        return

    df = pd.read_csv("model_predictions_log.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp", ascending=False)

    st.subheader("📊 Последние 20 предсказаний")
    st.dataframe(df.head(20), use_container_width=True)

    if len(df) > 30:
        st.subheader("📈 Дельта между Long и Short за последние дни")
        df["delta"] = abs(df["long_4h"] - df["short_4h"])
        st.line_chart(df.set_index("timestamp")["delta"])

    # 🎯 Оценка по high_confidence
    if "high_confidence" in df.columns and "eth_close" in df.columns:
        st.subheader("🔍 High Confidence Accuracy")
        df = df.sort_values("timestamp")  # важно для корректного .shift()
        df["future_close"] = df["eth_close"].shift(-4)
        df["actual_direction"] = (df["future_close"] > df["eth_close"]).map({True: "long", False: "short"})
        df["model_direction"] = (df["long_4h"] > df["short_4h"]).map({True: "long", False: "short"})

        confident_df = df[df["high_confidence"] == 1].copy()
        confident_df["correct"] = confident_df["actual_direction"] == confident_df["model_direction"]

        accuracy = confident_df["correct"].mean() if not confident_df.empty else 0
        st.metric("🎯 Точность уверенных предсказаний", f"{accuracy * 100:.2f}%")
        st.caption("Сравнение прогноза модели и реального движения цены через 4 часа на уверенных точках (prob > 55%, delta > 0.19)")

    st.caption("Данные собираются каждые 5 минут в фоновом режиме.")


if __name__ == "__main__":
    run()

