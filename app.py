import streamlit as st
from streamlit_option_menu import option_menu
import main_indicators
import evaluate_model

st.set_page_config(page_title="ETH AI App", layout="centered")

with st.sidebar:
    choice = option_menu("Навигация", ["📈 Прогноз ETH", "✅ Оценка модели"],
                         icons=["bar-chart", "check2-circle"], menu_icon="cast", default_index=0)

if choice == "📈 Прогноз ETH":
    main_indicators.run()
elif choice == "✅ Оценка модели":
    evaluate_model.run()
