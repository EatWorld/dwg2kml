# DWG 红线图 → 谷歌地球 KML

从 CAD 红线图（DWG）中自动提取地块坐标，转换为谷歌地球可识别的 KML 文件。

## 功能

- **自动读取 DWG** — 通过 ezdxf + ODA File Converter，无需手动转 DXF
- **双模式识别** — 自动判断红线图（有"红线"图层）或面积量算图（无红线图层）
- **自动坐标转换** — CGCS2000 高斯克吕格 → WGS84，自动识别带号
- **户名+面积匹配** — 面积量算图模式下自动关联 CAD 中的文字注记
- **红色边框输出** — KML 标准格式，双击即可用谷歌地球打开

## 快速开始

### 1. 安装依赖

```bash
pip install pyproj ezdxf
```

还需安装 [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)（免费）。

### 2. 运行

```bash
# 红线图模式（自动识别"红线"图层）
python scripts/extract_redline_from_dwg.py \
    --input 红线图.dwg \
    --output 输出.kml \
    --project-name "项目名"

# 面积量算图模式（自动提取宗地+户名+面积）
python scripts/extract_redline_from_dwg.py \
    --input 量算图.dwg \
    --output 输出.kml \
    --project-name "项目名"

# 东坐标不含带号时，需手动指定带号
python scripts/extract_redline_from_dwg.py \
    --input 红线图.dwg \
    --output 输出.kml \
    --zone 39  # 39=蚌埠/合肥, 40=上海/青岛, 38=武汉/北京
```

### 3. 查看

双击生成的 `.kml` 文件，谷歌地球自动打开并定位到红线范围。

## 支持的 CAD 图层

| 图层名 | 用途 | 脚本行为 |
|--------|------|---------|
| `红线` / `用地红线` | 项目红线边界 | 模式A：直接提取 |
| `0` | 宗地多段线 | 模式B：提取面积>1亩的宗地 |
| `姓名层` / `户名层` | 户主姓名 | 自动匹配到最近宗地 |
| `MJZJ` | 面积注记 | 自动匹配到最近宗地 |
| `TK` | 图框 | 自动排除 |

## 坐标系

- **源坐标系**：CGCS2000 高斯克吕格 3度带（东坐标含带号前缀）
- **目标坐标系**：WGS84（谷歌地球通用）
- **EPSG 公式**：`EPSG = 4509 + 带号`
- **典型带号**：39（117°E，蚌埠/合肥/济南）、40（120°E，上海/青岛）、38（114°E，武汉/北京）

## 文件结构

```
├── SKILL.md                           # 详细技术文档
├── README.md                          # 本文件
├── scripts/
│   ├── extract_redline_from_dwg.py    # 主脚本（DWG→KML全自动）
│   └── cgcs2000_to_kml.py             # 备用：CSV坐标输入
└── references/
    └── coordinate_systems.md          # CGCS2000/EPSG 参考表
```

## 许可证

MIT License

## 致谢

- [ezdxf](https://github.com/mozman/ezdxf) — DWG/DXF 文件读取
- [pyproj](https://github.com/pyproj4/pyproj) — 坐标系转换
- [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter) — DWG→DXF 转换引擎
