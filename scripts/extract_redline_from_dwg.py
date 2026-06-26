#!/usr/bin/env python3
"""
DWG 红线图/面积量算图 → 谷歌地球 KML（全自动版）
支持两种模式：
  模式A：有"红线"图层 → 提取红线多边形
  模式B：无红线图层 → 提取所有宗地 + 匹配户名/面积
流程：ezdxf(odafc)读取DWG → CGCS2000→WGS84 → 红色KML（无填充）

依赖：pip install ezdxf pyproj
ODA File Converter: https://www.opendesign.com/guestfiles/oda_file_converter
"""

import argparse
import math
import os
import shutil
import sys
import tempfile

import ezdxf
from ezdxf.addons import odafc
from pyproj import Transformer

ODA_PATHS = [
    r"C:\Program Files\ODA\ODAFileConverter 27.1.0\ODAFileConverter.exe",
    r"C:\Program Files\ODA\ODAFileConverter 27.1\ODAFileConverter.exe",
]
REDLINE_KEYWORDS = ['红线', '用地红线', 'redline', 'REDLINE', 'RedLine']
TEXT_LAYERS = ['姓名层', 'MJZJ', '面积层', '户名层', 'mainlayer']
AREA_MIN_MU = 0.5  # 面积量算图模式：最小宗地面积（亩）


def find_oda():
    for p in ODA_PATHS:
        if os.path.exists(p):
            return p
    return None


def setup_odafc():
    oda = find_oda()
    if not oda:
        print("❌ 未找到 ODA File Converter，请从以下地址下载安装：")
        print("   https://www.opendesign.com/guestfiles/oda_file_converter")
        sys.exit(1)
    ezdxf.options.set('odafc-addon', 'win_exec_path', oda)
    return oda


def collect_polylines(msp, layer_filter=None):
    polylines = []
    for e in msp.query('LWPOLYLINE'):
        if layer_filter and e.dxf.layer not in layer_filter:
            continue
        pts = list(e.get_points(format='xy'))
        if len(pts) < 3:
            continue
        area = 0.0
        for i in range(len(pts)):
            j = (i + 1) % len(pts)
            area += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
        area = abs(area) / 2.0
        polylines.append({
            'area': area,
            'mu': area / 666.67,
            'npts': len(pts),
            'closed': e.closed,
            'pts': pts,
            'layer': e.dxf.layer,
        })
    return polylines


def collect_texts(msp):
    """收集所有文字实体，返回 {图层: [(text, x, y), ...]}"""
    texts = {}
    for e in msp.query('TEXT'):
        layer = e.dxf.layer
        text = e.dxf.text.strip()
        if not text:
            continue
        pos = e.dxf.insert
        texts.setdefault(layer, []).append((text, pos[0], pos[1]))
    for e in msp.query('MTEXT'):
        layer = e.dxf.layer
        text = e.text.strip()
        if not text:
            continue
        pos = e.dxf.insert
        texts.setdefault(layer, []).append((text, pos[0], pos[1]))
    return texts


def centroid(pts):
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return cx, cy


def nearest_text(cx, cy, text_list):
    """找最近的文字"""
    if not text_list:
        return ''
    best, best_d = '', float('inf')
    for text, tx, ty in text_list:
        d = (cx - tx)**2 + (cy - ty)**2
        if d < best_d:
            best_d = d
            best = text
    return best


def determine_axes(pts):
    val0, val1 = pts[0]
    if val0 > 1e7 and val1 < 1e7:
        return [p[0] for p in pts], [p[1] for p in pts], 'X=东,Y=北'
    elif val1 > 1e7 and val0 < 1e7:
        return [p[1] for p in pts], [p[0] for p in pts], 'X=北,Y=东'
    else:
        return [p[0] for p in pts], [p[1] for p in pts], '默认X=东,Y=北'


def identify_zone(eastings):
    avg = sum(eastings) / len(eastings)
    if avg > 1e7:
        return int(str(int(avg))[:2])
    return 39  # 蚌埠默认


def to_wgs(pts_raw, zone):
    """原始多段线坐标 → WGS84坐标列表 [(lat, lon), ...]"""
    epsg = 4509 + zone
    t = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    prefix = zone * 1000000
    eastings, northings, _ = determine_axes(pts_raw)
    result = []
    for e, n in zip(eastings, northings):
        lon, lat = t.transform(e - prefix, n)
        if lat != float('inf'):
            result.append((lat, lon))
    return result


def kml_polygon(name, desc, wgs_pts, style='redLine'):
    """生成一个Placemark多边形"""
    lines = [
        '  <Placemark>',
        f'    <name>{name}</name>',
    ]
    if desc:
        lines.append(f'    <description><![CDATA[{desc}]]></description>')
    lines += [
        f'    <styleUrl>#{style}</styleUrl>',
        '    <Polygon>',
        '      <outerBoundaryIs>',
        '        <LinearRing>',
        '          <coordinates>',
    ]
    for lat, lon in wgs_pts:
        lines.append(f'            {lon:.8f},{lat:.8f},0')
    lines.append(f'            {wgs_pts[0][1]:.8f},{wgs_pts[0][0]:.8f},0')
    lines += [
        '          </coordinates>',
        '        </LinearRing>',
        '      </outerBoundaryIs>',
        '    </Polygon>',
        '  </Placemark>',
    ]
    return '\n'.join(lines)


def kml_wrapper(project_name, desc_text, placemarks_str, output_path):
    kml = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>{project_name}</name>
  <description>{desc_text}</description>

{placemarks_str}

  <Style id="redLine">
    <LineStyle><color>ff0000ff</color><width>2</width></LineStyle>
    <PolyStyle><fill>0</fill><outline>1</outline></PolyStyle>
  </Style>

</Document>
</kml>'''
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(kml)


def main():
    parser = argparse.ArgumentParser(description='DWG红线图/面积量算图 → KML')
    parser.add_argument('--input', required=True, help='DWG文件路径')
    parser.add_argument('--output', required=True, help='输出KML路径')
    parser.add_argument('--project-name', default='项目红线', help='项目名称')
    args = parser.parse_args()

    print("=" * 50)
    setup_odafc()

    # 中文路径处理
    input_path = os.path.abspath(args.input)
    has_non_ascii = any(ord(c) > 127 for c in input_path)
    tmp_dir = None
    if has_non_ascii:
        tmp_dir = tempfile.mkdtemp(prefix='dwg_work_')
        tmp_dwg = os.path.join(tmp_dir, 'redline.dwg')
        shutil.copy2(input_path, tmp_dwg)
        work_path = tmp_dwg
    else:
        work_path = input_path

    try:
        doc = odafc.readfile(work_path)
        msp = doc.modelspace()
        all_layers = set(e.dxf.layer for e in msp)

        # 收集文字（两种模式都需要）
        texts = collect_texts(msp)

        # 判断模式
        has_redline = any(kw in layer for kw in REDLINE_KEYWORDS for layer in all_layers)

        if has_redline:
            # === 模式A：红线图 ===
            print("模式: 红线图模式（有红线图层）")
            polylines = collect_polylines(msp)
            redlines = [p for p in polylines if any(kw in p['layer'] for kw in REDLINE_KEYWORDS)]
            redlines.sort(key=lambda x: x['area'], reverse=True)
            print(f"  红线: {len(redlines)} 条")

            zone = identify_zone(determine_axes(redlines[0]['pts'])[0])
            print(f"  带号: {zone}  EPSG: {4509+zone}")

            placemarks = []
            for i, r in enumerate(redlines):
                wgs = to_wgs(r['pts'], zone)
                mu = r['area'] / 666.67
                name = f'红线#{i+1} ({mu:.1f}亩)' if len(redlines) > 1 else f'{args.project_name} ({mu:.1f}亩)'
                placemarks.append(kml_polygon(name, '', wgs))

            kml_wrapper(args.project_name,
                        f'{len(redlines)}条红线 | CGCS2000→WGS84',
                        '\n\n'.join(placemarks), args.output)

        else:
            # === 模式B：面积量算图 ===
            print("模式: 面积量算图模式（无红线图层）")
            # 排除图框(TK)和红线图层，其余全部作为宗地候选
            exclude_layers = {'TK'} | set(REDLINE_KEYWORDS)
            polylines = [p for p in collect_polylines(msp)
                         if p['layer'] not in exclude_layers]
            parcels = [p for p in polylines if p['mu'] >= AREA_MIN_MU]
            parcels.sort(key=lambda x: x['area'], reverse=True)
            print(f"  宗地: {len(parcels)} 块")

            zone = identify_zone(determine_axes(parcels[0]['pts'])[0])
            print(f"  带号: {zone}  EPSG: {4509+zone}")

            # 匹配文字
            name_list = []
            for layer in TEXT_LAYERS:
                name_list.extend(texts.get(layer, []))

            # 分类：MJZJ 面积注记 vs 姓名层 户名
            area_texts = texts.get('MJZJ', [])
            owner_texts = []
            for layer in ['姓名层', '户名层', 'mainlayer']:
                # 0图层上也有可能有文字，但包含很多数字标注，只取姓名层和户名层
                if layer != '0':
                    owner_texts.extend(texts.get(layer, []))

            for p in parcels:
                cx, cy = centroid(p['pts'])
                p['area_text'] = nearest_text(cx, cy, area_texts)
                p['owner'] = nearest_text(cx, cy, owner_texts) if owner_texts else ''

            placemarks = []
            for i, p in enumerate(parcels):
                wgs = to_wgs(p['pts'], zone)
                if not wgs:
                    continue
                owner = p.get('owner', '').strip()
                area_text = p.get('area_text', '').strip()
                name = f'{owner} ({p["mu"]:.1f}亩)' if owner else f'宗地#{i+1} ({p["mu"]:.1f}亩)'
                desc_parts = []
                if owner:
                    desc_parts.append(f'户名: {owner}')
                if area_text:
                    desc_parts.append(f'面积: {area_text}')
                desc_parts.append(f'计算面积: {p["mu"]:.2f}亩 ({p["area"]:.1f}m²)')
                desc = '\n'.join(desc_parts)
                placemarks.append(kml_polygon(name, desc, wgs))

            with_owner = sum(1 for p in parcels if p.get('owner'))
            print(f"  有户名: {with_owner}块")
            total_mu = sum(p['mu'] for p in parcels)
            print(f"  总面积: {total_mu:.1f}亩")

            kml_wrapper(args.project_name,
                        f'{len(parcels)}块宗地 | 含户名+面积 | CGCS2000→WGS84',
                        '\n\n'.join(placemarks), args.output)

        print(f"\n✅ KML已生成: {args.output}")

    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)

    print("完成！双击KML即可用谷歌地球打开")


if __name__ == '__main__':
    main()
