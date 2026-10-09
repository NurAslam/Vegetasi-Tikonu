"""
Generate GEE tile URLs + NDVI classification for Desa Tikonu.
Run locally or via GitHub Actions to refresh tiles before they expire.
"""
import ee
import shapefile
import json
import os
import sys

# ── Auth ──────────────────────────────────────────────────────────────────
# GitHub Actions: credentials written from EE_CREDENTIALS secret
# Local: uses ~/.config/earthengine/credentials (already authenticated)
ee.Initialize(project='testing-460608')

# ── ROI ───────────────────────────────────────────────────────────────────
SHP = os.path.join(os.path.dirname(__file__), '..', 'shapefiles',
                   'Batas_Administrasi_Desa_Tikonu')
sf     = shapefile.Reader(SHP)
coords = [[pt[0], pt[1]] for pt in sf.shapes()[0].points]
roi    = ee.Geometry.Polygon([coords])

TOTAL_AREA_KM2 = 25.47
CLASS_PALETTE  = ['#d62728', '#ff7f0e', '#a8d96a', '#1a9850']
YEARS          = list(range(2015, 2027))


def classify_ndvi(ndvi_img):
    c1 = ndvi_img.lt(0.2).multiply(1)
    c2 = ndvi_img.gte(0.2).And(ndvi_img.lt(0.4)).multiply(2)
    c3 = ndvi_img.gte(0.4).And(ndvi_img.lt(0.6)).multiply(3)
    c4 = ndvi_img.gte(0.6).multiply(4)
    return c1.add(c2).add(c3).add(c4).rename('class')


def apply_scale_l8(img):
    return img.addBands(
        img.select('SR_B.').multiply(0.0000275).add(-0.2), None, True)


def process_year(y):
    start, end = f'{y}-01-01', f'{y}-12-31'
    scale  = 10
    sensor = None

    # Try Sentinel-2 first
    s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
          .filterBounds(roi).filterDate(start, end)
          .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)))
    ns2 = s2.size().getInfo()

    if ns2 > 0:
        median = s2.median()
        ndvi   = median.normalizedDifference(['B8', 'B4']).rename('NDVI').clip(roi)
        sensor = f'Sentinel-2 ({ns2} scene)'
        n_sc   = ns2
    else:
        # Fallback Landsat 8
        scale = 30
        l8 = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
              .filterBounds(roi).filterDate(start, end)
              .filter(ee.Filter.lt('CLOUD_COVER', 30))
              .map(apply_scale_l8))
        nl8 = l8.size().getInfo()
        if nl8 == 0:
            print(f'{y}: no data — skipped')
            return None
        median = l8.median()
        ndvi   = median.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI').clip(roi)
        sensor = f'Landsat 8 ({nl8} scene)'
        n_sc   = nl8

    cls_img  = classify_ndvi(ndvi)
    total_px = ndvi.reduceRegion(
        ee.Reducer.count(), roi, scale, maxPixels=1e9).get('NDVI').getInfo()

    def count_px(val):
        return cls_img.eq(val).reduceRegion(
            ee.Reducer.sum(), roi, scale, maxPixels=1e9
        ).get('class').getInfo() or 0

    n1, n2, n3, n4 = count_px(1), count_px(2), count_px(3), count_px(4)

    def pct(n):
        return round(n / total_px * 100, 2) if total_px else 0

    def area(n):
        return round(n / total_px * TOTAL_AREA_KM2, 3) if total_px else 0

    ndvi_tile = ndvi.getMapId({
        'min': 0.0, 'max': 0.8,
        'palette': ['#a50026', '#f46d43', '#fee08b', '#a6d96a', '#1a9850', '#006837']
    })['tile_fetcher'].url_format

    cls_tile = cls_img.getMapId({
        'min': 1, 'max': 4, 'palette': CLASS_PALETTE
    })['tile_fetcher'].url_format

    result = {
        'sensor':       sensor,
        'scenes':       n_sc,
        'tile_url':     ndvi_tile,
        'cls_tile_url': cls_tile,
        'veg_percent':  round(pct(n2) + pct(n3) + pct(n4), 2),
        'classes': {
            'non_veg': {'pct': pct(n1), 'area_km2': area(n1)},
            'jarang':  {'pct': pct(n2), 'area_km2': area(n2)},
            'sedang':  {'pct': pct(n3), 'area_km2': area(n3)},
            'rapat':   {'pct': pct(n4), 'area_km2': area(n4)},
        }
    }
    print(f'{y} [{sensor}] rapat={pct(n4):.1f}%', flush=True)
    return result


if __name__ == '__main__':
    results = {}
    for y in YEARS:
        r = process_year(y)
        results[str(y)] = r

    out_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'tiles.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nSaved → {out_path}')
