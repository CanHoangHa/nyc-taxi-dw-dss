"""Shared contrast for dashboard charts and compact chart headers."""
import altair as alt
import streamlit as st


def chart_palette():
    return '#1764b5','#64748b'


def show_chart(chart, **kwargs):
    # A chart owns its light background and text colours. Streamlit's client
    # theme can otherwise override these with colours from the previous theme.
    return st.altair_chart(chart,theme=None,**kwargs)


@alt.theme.register('taxi_readable',enable=True)
def readable_charts():
    text = '#334155'
    return {'config': {'background':'#ffffff','axis': {'labelColor':text,'titleColor':text,'labelFontSize':12,
                                'titleFontSize':13,'titlePadding':12,
                                'gridColor':'#e2e8f0'},
                       'legend': {'labelColor':text,'titleColor':text,'labelFontSize':12}}}


def right_button(label, **kwargs):
    with st.container(horizontal=True,horizontal_alignment='right'):
        return st.button(label, **kwargs)
