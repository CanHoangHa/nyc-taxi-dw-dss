# Taxi zone boundaries

`taxi_zones.geojson` is a local display asset, joined using `location_id`.
Source: [NYC TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page),
[Taxi Zone Shapefile](https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip).
Downloaded 1 November 2026. Includes all 263 unique IDs, 1–263. Codes 264/265
have no polygon; their pickups remain in dashboard totals and are reported
separately below the map.

Preparation: pyshp 3.1.6 reads the source shapefile; Shapely 2.2.0 simplifies
each geometry at 20 US survey feet with topology preservation. pyproj 3.7.2
transforms the source `.prj` CRS to EPSG:4326 with `always_xy=True`.
Coordinates are rounded to six decimal places. This approximation is for
visualization only, never for assigning trips to zones. Source names and
boroughs are retained; counts come exclusively from the mart.

SHA256 of source ZIP:
`f6d711917bb4340f8f644d5366c51665489eb2d426dd1a4a55677721ae5adf17`

SHA256 of GeoJSON:
`8c027937a98c1770e6c3a1231ed2fc12dfa80f25c37a19118fbb2de632055334`

The app reads this file locally. Background tiles use CARTO/OpenStreetMap
through Pydeck and need internet access; no API key is required for the
standard basemap. The boundary conversion libraries are not runtime dependencies.

`taxi_boroughs.geojson` groups the same source geometries by borough (including
EWR as a separate reference area). Original projected shapes are unioned before
the same 20-foot simplification, WGS84 transformation and six-decimal rounding.
This is an OLAP display aggregate, not an independent administrative boundary dataset.
Its SHA256 is
`b74d347f2164d05bc8729f94fee6d594e6917fd7efdbc1c428a87e12599c41e8`.

The `*_labels.json` files contain one interior label anchor per area, computed
with Shapely `representative_point()` on its largest polygon, rounded to six
decimals. They do not affect geometry, counts or ranking. The map uses CARTO
Positron without background labels; a separate text layer names active
boroughs or the top five positive-pickup zones, with plain names and ties
ordered by LocationID. Names use bold dark text on white background boxes;
overlap does not remove a top-five name. Every area remains available
through hover. Zooming and panning do not change the pickup totals.
