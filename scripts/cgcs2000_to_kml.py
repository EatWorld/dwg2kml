#!/usr/bin/env python3
"""
CGCS2000 高斯克吕格坐标 → WGS84 → KML 转换脚本
适用于征迁红线图、宗地图等 CAD 界址点坐标转换

使用方式：
  1. CSV输入：python cgcs2000_to_kml.py --input coords.csv --output 红线.kml --zone 39
  2. 内联坐标：编辑本文件底部 points_raw 列表后直接运行

CSV格式（无表头）：
  J1,3641349.088,39530339.816
  J2,3641318.711,39530377.397
  ...

依赖：pip install pyproj
"""

import argparse
import csv
import sys
from pathlib import Path
from pyproj import Transformer


# 3度带带号 → EPSG 对照表（CGCS2000）
ZONE_TO_EPSG = {
    25: 4534, 26: 4535, 27: 4536, 28: 4537, 29: 4538,
    30: 4539, 31: 4540, 32: 4541, 33: 4542, 34: 4543,
    35: 4544, 36: 4545, 37: 4546, 38: 4547, 39: 4548,
    40: 4549, 41: 4550, 42: 4551, 43: 4552, 44: 4553,
    45: 4554,
}

# 带号 → 中央经线（3度带：CM = zone * 3）
def zone_to_central_meridian(zone):
    return zone * 3


def get_transformer(zone):
    """根据带号获取 CGCS2000 → WGS84 转换器"""
    if zone not in ZONE_TO_EPSG:
        raise ValueError(f"不支持的带号 {zone}，支持范围 25-45（3度带）")
    epsg = ZONE_TO_EPSG[zone]
    return Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)


def convert_point(north_x, east_y, zone, transformer):
    """
    转换单个点
    关键：Y值带带号前缀，必须去掉
      east_y = 39530339.816 (带号39)
      true_easting = 39530339.816 - 39000000 = 530339.816
    """
    zone_prefix = zone * 1000000  # 如 39 → 39000000
    true_easting = east_y - zone_prefix
    # pyproj 参数顺序：(easting=东坐标, northing=北坐标)
    lon, lat = transformer.transform(true_easting, north_x)
    if lat == float('inf') or lon == float('inf'):
        raise ValueError(
            f"坐标转换失败(超出投影范围)：X={north_x}, Y={east_y}, 带号={zone}\n"
            f"请检查带号是否正确。带号 = Y值前2位，3度带中央经线 = 带号×3"
        )
    return lat, lon


def load_points_csv(csv_path):
    """从CSV加载坐标点：name, north_x, east_y"""
    points = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue
            name = row[0].strip()
            if not name or name.startswith('#'):
                continue
            try:
                north_x = float(row[1])
                east_y = float(row[2])
                points.append((name, north_x, east_y))
            except ValueError:
                continue  # 跳过表头或非数据行
    return points


def compute_area_mu(coords_wgs84):
    """用球面近似计算多边形面积（亩），coords_wgs84=[(lat, lon), ...]"""
    n = len(coords_wgs84)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += coords_wgs84[i][1] * coords_wgs84[j][0]
        area -= coords_wgs84[j][1] * coords_wgs84[i][0]
    abs_area = abs(area) / 2.0
    # 用平均纬度估算度→米转换
    avg_lat = sum(c[0] for c in coords_wgs84) / n
    import math
    deg_to_m_lat = 111320.0
    deg_to_m_lng = 111320.0 * math.cos(math.radians(avg_lat))
    return abs_area * deg_to_m_lat * deg_to_m_lng / 10000  # 转亩


def generate_kml(points_wgs84, project_name, output_path, key_indices=None):
    """
    生成KML文件
    points_wgs84: [(name, lat, lon), ...]
    key_indices: 需要标注点位的索引列表（None=标注全部主要拐点）
    """
    if key_indices is None:
        # 默认标注首尾及部分拐点
        key_indices = [0, len(points_wgs84) // 4, len(points_wgs84) // 2,
                       3 * len(points_wgs84) // 4, len(points_wgs84) - 1]

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
    lines.append('<Document>')
    lines.append(f'  <name>{project_name}</name>')
    lines.append(f'  <description>界址点 {len(points_wgs84)} 个 | CGCS2000→WGS84</description>')

    # 红线多边形
    lines.append('  <Placemark>')
    lines.append('    <name>项目红线范围</name>')
    lines.append('    <styleUrl>#redLine</styleUrl>')
    lines.append('    <Polygon>')
    lines.append('      <outerBoundaryIs>')
    lines.append('        <LinearRing>')
    lines.append('          <coordinates>')
    for _, lat, lon in points_wgs84:
        lines.append(f'            {lon:.8f},{lat:.8f},0')
    # 闭合
    lines.append(f'            {points_wgs84[0][2]:.8f},{points_wgs84[0][1]:.8f},0')
    lines.append('          </coordinates>')
    lines.append('        </LinearRing>')
    lines.append('      </outerBoundaryIs>')
    lines.append('    </Polygon>')
    lines.append('  </Placemark>')

    # 关键拐点标注
    for idx in key_indices:
        if 0 <= idx < len(points_wgs84):
            name, lat, lon = points_wgs84[idx]
            lines.append('  <Placemark>')
            lines.append(f'    <name>{name}</name>')
            lines.append('    <styleUrl>#pointStyle</styleUrl>')
            lines.append('    <Point>')
            lines.append(f'      <coordinates>{lon:.8f},{lat:.8f},0</coordinates>')
            lines.append('    </Point>')
            lines.append('  </Placemark>')

    # 样式
    lines.append('  <Style id="redLine">')
    lines.append('    <LineStyle><color>ffff0000</color><width>3</width></LineStyle>')
    lines.append('    <PolyStyle><color>30ff0000</color><fill>1</fill><outline>1</outline></PolyStyle>')
    lines.append('  </Style>')
    lines.append('  <Style id="pointStyle">')
    lines.append('    <IconStyle><scale>0.6</scale>')
    lines.append('      <Icon><href>http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png</href></Icon>')
    lines.append('    </IconStyle>')
    lines.append('    <LabelStyle><scale>0.7</scale></LabelStyle>')
    lines.append('  </Style>')

    lines.append('</Document>')
    lines.append('</kml>')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description='CGCS2000高斯克吕格坐标转KML')
    parser.add_argument('--input', help='CSV文件路径（格式：name,north_x,east_y）')
    parser.add_argument('--output', required=True, help='输出KML文件路径')
    parser.add_argument('--zone', type=int, required=True,
                        help='3度带带号（Y值前2位，如39）')
    parser.add_argument('--project-name', default='项目红线', help='项目名称')
    args = parser.parse_args()

    transformer = get_transformer(args.zone)
    cm = zone_to_central_meridian(args.zone)
    print(f"坐标系：CGCS2000 3度带第{args.zone}带，中央经线 {cm}°E (EPSG:{ZONE_TO_EPSG[args.zone]})")

    # 加载坐标点
    if args.input:
        points = load_points_csv(args.input)
        print(f"从 {args.input} 加载 {len(points)} 个点")
    else:
        print("错误：未指定 --input，请提供CSV文件或编辑脚本底部内联坐标", file=sys.stderr)
        sys.exit(1)

    if not points:
        print("错误：未加载到任何坐标点", file=sys.stderr)
        sys.exit(1)

    # 转换
    print("正在转换坐标...")
    wgs84_points = []
    for name, nx, ey in points:
        lat, lon = convert_point(nx, ey, args.zone, transformer)
        wgs84_points.append((name, lat, lon))

    # 验证输出
    first = wgs84_points[0]
    last = wgs84_points[-1]
    print(f"首点 {first[0]}: N={first[1]:.8f}° E={first[2]:.8f}°")
    print(f"末点 {last[0]}: N={last[1]:.8f}° E={last[2]:.8f}°")

    # 面积估算
    area = compute_area_mu([(p[1], p[2]) for p in wgs84_points])
    print(f"红线范围约 {area:.1f} 亩")

    # 生成KML
    generate_kml(wgs84_points, args.project_name, args.output)
    print(f"\n✅ KML已生成: {args.output}")
    print("双击该文件即可用谷歌地球打开")


if __name__ == '__main__':
    main()
