"""Map scope, sparse zeros, and pickup totals remain consistent."""
from datetime import date
import unittest
from dashboard.zone_map import pickup_features, zone_boundaries


class ZoneMapTests(unittest.TestCase):
    def test_map_fits_nyc_and_legend_uses_svg_image(self):
        from unittest.mock import patch
        from dashboard.zone_map import fitted_map_view, show_map_legend
        data,points,_=pickup_features([],geo_level='borough')
        view=fitted_map_view(points)
        self.assertTrue(8<view.zoom<12)
        self.assertTrue(-74.3<view.longitude<-73.6)
        self.assertTrue(40.4<view.latitude<41)
        with patch('dashboard.zone_map.st.image') as image, \
             patch('dashboard.zone_map.st.html') as html:
            show_map_legend(data,0)
        self.assertIn('<linearGradient',image.call_args.args[0])
        html.assert_not_called()

    def test_legend_ticks_follow_actual_log_colour_scale(self):
        from dashboard.zone_map import legend_ticks, map_legend_svg
        for maximum in (0,1,2,567687):
            ticks=legend_ticks(maximum)
            self.assertEqual(ticks[-1],maximum)
            self.assertEqual(ticks,sorted(set(ticks)))
            self.assertIn(f'{maximum:,}',map_legend_svg(maximum))
        self.assertGreaterEqual(len(legend_ticks(567687)),5)
        self.assertNotIn('nan',map_legend_svg(0).lower())

    def test_labels_only_show_active_boroughs_or_top_five_zones(self):
        from dashboard.zone_map import map_labels
        data,_,_=pickup_features([dict(pickup_location_id=i,trip_count=i) for i in range(1,16)])
        before=[f['properties']['trip_count'] for f in data['features']]
        labels=map_labels(data,'zone')
        self.assertEqual(len(labels),5)
        expected={f['properties']['zone_name'] for f in data['features']
                  if f['properties']['location_id'] in range(11,16)}
        self.assertEqual({' '.join(p['label'].split()) for p in labels},expected)
        self.assertEqual(before,[f['properties']['trip_count'] for f in data['features']])
        boroughs,_,_=pickup_features([dict(borough='Manhattan',trip_count=10)],borough='Manhattan',geo_level='borough')
        self.assertEqual([p['label'] for p in map_labels(boroughs,'borough')],['Manhattan'])

    def test_single_selected_zero_zone_still_has_a_name(self):
        from dashboard.zone_map import map_labels
        data,_,_=pickup_features([],borough='Manhattan',zone_ids=(161,))
        self.assertEqual([p['label'] for p in map_labels(data,'zone')],['Midtown Center'])

    def test_queens_top_three_are_never_hidden_by_neighbours(self):
        from dashboard.zone_map import map_labels
        rows=[dict(pickup_location_id=z,trip_count=count) for z,count in
              [(132,3794),(138,1988),(70,303),(226,136),(145,87),(193,60)]]
        data,_,_=pickup_features(rows,borough='Queens')
        labels=map_labels(data,'zone')
        self.assertEqual([p['node'] for p in labels],['132','138','70','226','145'])
        self.assertEqual(' '.join(labels[2]['label'].split()),'East Elmhurst')

    def test_borough_totals_zero_and_unmapped_are_distinct(self):
        rows=[dict(borough='Manhattan',trip_count=100),dict(borough='Unknown',trip_count=7)]
        data,_,unmapped=pickup_features(rows,geo_level='borough')
        props={f['properties']['borough']:f['properties'] for f in data['features']}
        self.assertEqual(props['Manhattan']['trip_count'],100)
        self.assertEqual(props['Queens']['trip_count'],0)
        self.assertEqual(unmapped,7)
        self.assertEqual(sum(p['trip_count'] or 0 for p in props.values())+unmapped,107)
        scoped,_,_=pickup_features([dict(borough='Manhattan',trip_count=100)],
                                  zone_ids=(161,),geo_level='borough')
        self.assertEqual({f['properties']['borough'] for f in scoped['features']
                          if f['properties']['trip_count'] is not None},{'Manhattan'})

    def test_map_selection_returns_area_and_rejects_outside_scope(self):
        from unittest.mock import patch
        from dashboard.zone_map import show_pickup_map
        features=zone_boundaries('borough')['features']
        index=next(i for i,f in enumerate(features) if f['properties']['borough']=='Manhattan')
        event={'selection':{'indices':{'pickup-areas':[index]}}}
        with patch('dashboard.zone_map.st.pydeck_chart',return_value=event), \
             patch('dashboard.zone_map.st.html') as css, patch('dashboard.zone_map.st.caption'):
            self.assertEqual(show_pickup_map([dict(borough='Manhattan',trip_count=100)],geo_level='borough'),'Manhattan')
            self.assertIsNone(show_pickup_map([],borough='Queens',geo_level='borough'))
        self.assertTrue(any('transform: none !important' in call.args[0] for call in css.call_args_list))

    def test_tooltip_fields_resolve_in_streamlit_geojson_properties(self):
        from unittest.mock import patch
        from string import Formatter
        from dashboard.zone_map import show_pickup_map
        from streamlit.elements.deck_gl_json_chart import _get_pydeck_tooltip
        with patch('dashboard.zone_map.st.pydeck_chart') as chart, \
             patch('dashboard.zone_map.st.subheader'), patch('dashboard.zone_map.st.caption'):
            show_pickup_map([dict(pickup_location_id=161,trip_count=1234)])
        deck = chart.call_args.args[0]
        import json
        self.assertIs(json.loads(deck.to_json())['views'][0]['controller'],True)
        text_layer=json.loads(deck.layers[1].to_json())
        self.assertEqual(text_layer['fontFamily'],'Arial')
        self.assertTrue(text_layer['background'])
        self.assertEqual(text_layer['getBackgroundColor'],[255,255,255,250])
        template = _get_pydeck_tooltip(deck)['text']
        fields = [field for _,field,_,_ in Formatter().parse(template) if field]
        # Streamlit resolves direct keys on object.properties, not dotted paths.
        self.assertEqual(set(fields),{'area_label','borough','pickups'})
        for feature in deck.layers[0].data['features']:
            rendered = template.format_map(feature['properties'])
            self.assertNotIn('{',rendered)
            if feature['properties']['location_id']==161:
                self.assertIn('Midtown Center',rendered)
                self.assertIn('Borough: Manhattan',rendered)
                self.assertIn('1,234',rendered)

    def test_reference_is_complete_and_has_geographic_coordinates(self):
        features=zone_boundaries()['features']
        self.assertEqual({f['properties']['location_id'] for f in features},set(range(1,264)))
        self.assertEqual(len(features),263)
        for f in features:
            self.assertIn(f['geometry']['type'],('Polygon','MultiPolygon'))
        _,points,_=pickup_features([])
        self.assertTrue(all(-75<x<-73 and 40<y<42 for x,y in points))

    def test_zero_is_distinct_from_outside_filters_and_source_not_mutated(self):
        rows=[dict(pickup_location_id=161,trip_count=100)]
        data,points,unmapped=pickup_features(rows,'Manhattan',(161,162))
        props={f['properties']['location_id']:f['properties'] for f in data['features']}
        self.assertEqual(props[161]['trip_count'],100)
        self.assertEqual(props[162]['trip_count'],0)
        self.assertIsNone(props[132]['trip_count'])
        self.assertEqual(props[132]['pickups'],'Outside filters')
        self.assertEqual(len({tuple(props[i]['fill_color']) for i in (161,162,132)}),3)
        self.assertEqual(unmapped,0)
        self.assertTrue(points)
        self.assertNotIn('trip_count',zone_boundaries()['features'][0]['properties'])

    def test_unknown_pickups_are_accounted_for_without_fabricating_geometry(self):
        rows=[dict(pickup_location_id=161,trip_count=100),dict(pickup_location_id=264,trip_count=7)]
        data,_,unmapped=pickup_features(rows)
        self.assertEqual(unmapped,7)
        self.assertEqual(sum(f['properties']['trip_count'] or 0 for f in data['features'])+unmapped,107)

    def test_borough_focus_fits_selected_area(self):
        _,all_points,_=pickup_features([])
        _,manhattan,_=pickup_features([],'Manhattan')
        self.assertLess(len(manhattan),len(all_points))
        self.assertLess(max(x for x,y in manhattan)-min(x for x,y in manhattan),max(x for x,y in all_points)-min(x for x,y in all_points))

    def test_real_mart_matches_kpi_across_scopes(self):
        import os
        if os.getenv('RUN_ANALYTICS_TESTS')!='1':
            self.skipTest('set RUN_ANALYTICS_TESTS=1 for real mart reconciliation')
        from dashboard.analytics_repository import AnalyticsRepository
        repository=AnalyticsRepository()
        for borough,zones,hours in ((None,(),(0,23)),('Manhattan',(),(6,9)),('Queens',(132,),(8,8)),('Bronx',(),(0,0))):
            rows,truncated=repository.olap(date(2024,1,1),date(2024,4,30),time_level='all',geo_level='zone',borough=borough,zone_ids=zones,hour_range=hours)
            self.assertFalse(truncated)
            data,_,unmapped=pickup_features(rows,borough,zones)
            total=sum(f['properties']['trip_count'] or 0 for f in data['features'])+unmapped
            self.assertEqual(total,repository.summary(date(2024,1,1),date(2024,4,30),borough=borough,zone_ids=zones,hour_range=hours)['trip_count'])
            borough_rows,_=repository.olap(date(2024,1,1),date(2024,4,30),time_level='all',geo_level='borough',borough=borough,zone_ids=zones,hour_range=hours)
            borough_data,_,missing=pickup_features(borough_rows,borough,zones,geo_level='borough')
            self.assertEqual(sum(f['properties']['trip_count'] or 0 for f in borough_data['features'])+missing,total)
