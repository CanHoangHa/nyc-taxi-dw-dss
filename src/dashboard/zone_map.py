"""Pickup maps share the OLAP geography path and applied scope."""
from copy import deepcopy
from functools import lru_cache
import json
import math
from pathlib import Path
from textwrap import fill

import pydeck as pdk
import streamlit as st


def pickup_color(count, maximum):
    if count is None:
        return [148,163,184,70]
    if count == 0:
        return [248,250,252,255]
    intensity = math.log1p(count) / math.log1p(maximum) if maximum else 0
    return [round(224-212*intensity),round(242-170*intensity),round(254-114*intensity),235]


def legend_ticks(maximum):
    if maximum <= 1:
        return [maximum]
    ticks = [1]
    low, high = math.log(2), math.log1p(maximum)
    for fraction in (0.25,0.5,0.75):
        value = math.expm1(low + fraction*(high-low))
        step = 10 ** math.floor(math.log10(value))
        rounded = int(round(value/step)*step)
        if ticks[-1] < rounded < maximum:
            ticks.append(rounded)
    return ticks + [maximum]


def map_legend_svg(maximum):
    stops = []
    for index in range(11):
        value = math.expm1(math.log(2)+(index/10)*(math.log1p(maximum)-math.log(2))) if maximum > 1 else maximum
        r,g,b,a = pickup_color(value,maximum)
        stops.append(f'<stop offset="{index*10}%" stop-color="rgb({r},{g},{b})" stop-opacity="{a/255}"/>')
    marks = []
    for value in legend_ticks(maximum):
        fraction = (math.log1p(value)-math.log(2))/(math.log1p(maximum)-math.log(2)) if maximum > 1 else 0
        y = 254-220*fraction
        marks.append(f'<line x1="30" x2="36" y1="{y}" y2="{y}" stroke="#64748b"/>'
                     f'<text x="41" y="{y+4}" font-size="12">{value:,}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 155 338" role="img" aria-label="Valid pickups colour legend"
      style="width:155px;max-width:100%;font-family:Arial,sans-serif;fill:#1e293b">
      <defs><linearGradient id="pickup-scale" x1="0" y1="1" x2="0" y2="0">{''.join(stops)}</linearGradient></defs>
      <text x="8" y="17" font-size="13" font-weight="600">Valid pickups</text>
      <rect x="8" y="34" width="22" height="220" fill="url(#pickup-scale)"/>{''.join(marks)}
      <rect x="8" y="280" width="12" height="12" fill="#f8fafc" stroke="#94a3b8"/><text x="27" y="291" font-size="12">0</text>
      <rect x="8" y="308" width="12" height="12" fill="#e3e6eb" stroke="#94a3b8"/><text x="27" y="319" font-size="12">Outside selection</text>
      </svg>'''


def show_map_legend(data, unmapped):
    maximum = max((f['properties']['trip_count'] or 0 for f in data['features']),default=0)
    # st.html sanitises SVG gradients; st.image keeps the complete SVG intact.
    st.image(map_legend_svg(maximum),width=155)


@lru_cache(maxsize=2)
def zone_boundaries(geo_level='zone'):
    filename = 'taxi_boroughs.geojson' if geo_level == 'borough' else 'taxi_zones.geojson'
    return json.loads((Path(__file__).parent / 'assets' / filename).read_text(encoding='utf-8'))


def _points(coordinates):
    if isinstance(coordinates[0], (int, float)):
        yield coordinates[:2]
    else:
        for part in coordinates:
            yield from _points(part)


@lru_cache(maxsize=2)
def label_positions(geo_level):
    name = 'taxi_boroughs_labels.json' if geo_level == 'borough' else 'taxi_zones_labels.json'
    return json.loads((Path(__file__).parent / 'assets' / name).read_text(encoding='utf-8'))


def map_labels(data, geo_level):
    active = [f['properties'] for f in data['features'] if f['properties']['trip_count'] is not None]
    ranked = geo_level == 'zone' and len(active) > 1
    if ranked:
        active = sorted((p for p in active if p['trip_count'] > 0),
                        key=lambda p: (-p['trip_count'],int(p['node'])))[:5]
    positions = label_positions(geo_level)
    labels = [dict(position=positions[p['node']], node=p['node'],
                   label=fill(p['borough'] if geo_level == 'borough' else p['zone_name'],width=18))
              for index,p in enumerate(active)]
    return labels


def pickup_features(rows, borough=None, zone_ids=(), geo_level='zone'):
    """Sparse zeros apply only inside the current exploration scope."""
    data = deepcopy(zone_boundaries(geo_level))
    field = 'borough' if geo_level == 'borough' else 'pickup_location_id'
    counts = {row[field]: int(row['trip_count']) for row in rows}
    selected = set(zone_ids)
    selected_boroughs = {f['properties']['borough'] for f in zone_boundaries()['features']
                         if f['properties']['location_id'] in selected}
    mapped_ids = {f['properties']['borough' if geo_level == 'borough' else 'location_id']
                  for f in data['features']}
    maximum = max((count for identifier,count in counts.items() if identifier in mapped_ids), default=0)
    bounds, mapped_total = [], 0
    for feature in data['features']:
        props = feature['properties']
        identifier = props['borough' if geo_level == 'borough' else 'location_id']
        inside = (borough is None or props['borough'] == borough)
        inside &= not selected or (props['borough'] in selected_boroughs if geo_level == 'borough' else identifier in selected)
        count = counts.get(identifier, 0) if inside else None
        props['node'] = str(identifier)
        props['area_label'] = (props['borough'] if geo_level == 'borough'
                               else f"{props['zone_name']} (#{identifier})")
        props['pickups'] = f'{count:,}' if inside else 'Outside filters'
        props['trip_count'] = count
        if inside:
            mapped_total += count
            props['fill_color'] = pickup_color(count,maximum)
            bounds.extend(_points(feature['geometry']['coordinates']))
        else:
            props['fill_color'] = pickup_color(None,maximum)
    return data, bounds, sum(counts.values()) - mapped_total


def fitted_map_view(points):
    if not points:
        return pdk.ViewState(latitude=40.72,longitude=-73.94,zoom=9)
    xs = [(lon+180)/360 for lon,lat in points]
    ys = [(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2 for lon,lat in points]
    span_x,span_y = max(xs)-min(xs),max(ys)-min(ys)
    zoom = min(math.log2(760/(512*max(span_x,1e-9))),
               math.log2(390/(512*max(span_y,1e-9))),13)
    return pdk.ViewState(longitude=(min(xs)+max(xs))/2*360-180,
        latitude=math.degrees(math.atan(math.sinh(math.pi*(1-min(ys)-max(ys))))),zoom=zoom)


def show_pickup_map(rows, borough=None, zone_ids=(), *, geo_level='zone', key='olap_map', selectable=True):
    data, points, unmapped = pickup_features(rows, borough, zone_ids, geo_level)
    view = fitted_map_view(points)
    labels = map_labels(data,geo_level)
    deck = pdk.Deck(
        layers=[pdk.Layer('GeoJsonLayer',data,id='pickup-areas',pickable=True,auto_highlight=True,
                         get_fill_color='properties.fill_color',get_line_color=[90,105,120,160],
                         line_width_min_pixels=0.7,stroked=True,filled=True),
                pdk.Layer('TextLayer',labels,id='pickup-labels',pickable=False,
                          get_position='position',get_text='label',get_size=14,
                          get_color=[15,23,42],font_family="'Arial'",font_weight=600,
                          background=True,get_background_color=[255,255,255,250],
                          background_padding=[4,2])],
        initial_view_state=view,map_provider='carto',
        map_style='https://basemaps.cartocdn.com/gl/positron-nolabels-gl-style/style.json',
        tooltip={'text':'{area_label}\nBorough: {borough}\nValid pickups: {pickups}',
                 'style': {'backgroundColor':'#17212f','color':'#ffffff','fontSize':'14px'}},
    )
    # Dock inside the map so scrolling/fullscreen cannot clip a floating tooltip.
    st.html('''<style>.stDeckGlJsonChart .deck-tooltip {
        transform: none !important; top: auto !important; bottom: 12px !important;
        left: 12px !important; max-width: calc(100% - 24px); box-sizing: border-box;
        z-index: 10 !important;
    }</style>''')
    map_column, legend_column = st.columns([6,1])
    with map_column:
        event = st.pydeck_chart(deck,height=480,key=f'{key}_default_controls',on_select='rerun' if selectable else 'ignore')
    with legend_column:
        show_map_legend(data,unmapped)
    indices = event.get('selection',{}).get('indices',{}).get('pickup-areas',[]) if selectable and isinstance(event,dict) else []
    if indices and 0 <= indices[0] < len(data['features']):
        props = data['features'][indices[0]]['properties']
        if props['trip_count'] is not None:
            return props['node']
    return None
