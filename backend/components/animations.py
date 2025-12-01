import json
import streamlit as st
from streamlit_lottie import st_lottie

# ----------------------------
# Lottie Loader
# ----------------------------
def load_lottie_animation(animation_type: str):
    animations = {
        "thinking": {
            "v": "5.7.4",
            "fr": 30,
            "ip": 0,
            "op": 120,
            "w": 200,
            "h": 200,
            "nm": "thinking",
            "ddd": 0,
            "assets": [],
            "layers": [
                {
                    "ty": 4,
                    "nm": "circle",
                    "sr": 1,
                    "ks": {
                        "o": {"a": 0, "k": 100},
                        "r": {"a": 1, "k": [{"t": 0, "s": 0}, {"t": 120, "s": 360}]},
                        "p": {"a": 0, "k": [100, 100, 0]},
                        "a": {"a": 0, "k": [0, 0, 0]},
                        "s": {"a": 0, "k": [100, 100, 100]},
                    },
                    "shapes": [
                        {"ty": "el", "p": {"a": 0, "k": [0, 0]}, "s": {"a": 0, "k": [150, 150]}}
                    ],
                }
            ],
        },
        "loading": {
            "v": "5.7.4",
            "fr": 30,
            "ip": 0,
            "op": 60,
            "w": 200,
            "h": 200,
            "nm": "loading",
            "ddd": 0,
            "assets": [],
            "layers": [
                {
                    "ty": 4,
                    "nm": "spinner",
                    "sr": 1,
                    "ks": {
                        "o": {"a": 0, "k": 100},
                        "r": {"a": 1, "k": [{"t": 0, "s": 0}, {"t": 60, "s": 360}]},
                        "p": {"a": 0, "k": [100, 100, 0]},
                        "a": {"a": 0, "k": [0, 0, 0]},
                        "s": {"a": 0, "k": [100, 100, 100]},
                    },
                    "shapes": [
                        {"ty": "rc", "p": {"a": 0, "k": [0, 0]}, "s": {"a": 0, "k": [150, 150]}, "r": {"a": 0, "k": 20}}
                    ],
                }
            ],
        },
    }
    return animations.get(animation_type, {})


def render_lottie(animation_type, height=150, key=None):
    """Render Lottie animation inside Streamlit."""
    animation = load_lottie_animation(animation_type)
    if animation:
        st_lottie(animation, height=height, key=key)


# ----------------------------
# HTML Animations
# ----------------------------
def render_typing_indicator():
    html = """
    <style>
    .typing {display: flex; gap: 4px; align-items: center;}
    .dot {width: 8px; height: 8px; background: #4CAF50; border-radius: 50%; animation: blink 1.4s infinite both;}
    .dot:nth-child(2) {animation-delay: 0.2s;}
    .dot:nth-child(3) {animation-delay: 0.4s;}
    @keyframes blink {0%, 80%, 100% {transform: scale(0);} 40% {transform: scale(1);}}
    </style>
    <div class="typing"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_pulse_animation():
    html = """
    <style>
    .pulse {width: 20px; height: 20px; background: #FF5722; border-radius: 50%;
            animation: pulse 1.5s infinite;}
    @keyframes pulse {0% {transform: scale(1); opacity: 1;}
                      50% {transform: scale(1.5); opacity: 0.6;}
                      100% {transform: scale(1); opacity: 1;}}
    </style>
    <div class="pulse"></div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_loading_spinner():
    html = """
    <style>
    .spinner {border: 4px solid rgba(0,0,0,0.1);
              width: 36px; height: 36px; border-radius: 50%;
              border-left-color: #09f; animation: spin 1s linear infinite;}
    @keyframes spin {to {transform: rotate(360deg);}}
    </style>
    <div class="spinner"></div>
    """
    st.markdown(html, unsafe_allow_html=True)
