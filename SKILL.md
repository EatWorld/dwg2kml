---
name: dwg-redline-to-google-earth
description: 将CAD红线图/面积量算图(DWG)中的地块自动提取坐标并生成红色KML文件导入谷歌地球。支持两种模式：(1)有"红线"图层的红线图 → 提取红线多边形；(2)无红线图层的面积量算图 → 提取所有宗地并匹配户名+面积。自动从DWG提取LWPOLYLINE坐标，CGCS2000高斯克吕格投影转WGS84，生成红色边框KML（无填充）。
---

# DWG 红线图/面积量算图 → 谷歌地球 KML（全自动版）

## 适用场景

将征迁项目红线图、土地面积量算图等 DWG 文件中的地块转换为谷歌地球可识别的 KML 文件。

### 两种模式

**模式 A：红线图**（DWG 有"红线"/"用地红线"图层）
- 提取红线图层所有闭合多段线
- 每条红线作为独立 Placemark，标注面积

**模式 B：面积量算图**（DWG 无"红线"图层，地块在"0"图层，文字在"姓名层"/"MJZJ"图层）
- 提取所有面积>1亩的宗地多段线
- 自动匹配户名（姓名层 TEXT/MTEXT）和面积注记（MJZJ TEXT）
- 命名格式：`户名 (X.X亩)`，点击可看详细面积信息

## 依赖（一次性安装，后续复用）

```bash
pip install pyproj ezdxf
```

还需安装 ODA File Converter（Windows MSI）：
- 下载: https://www.opendesign.com/cn/guestfiles/oda_file_converter
- 默认路径: `C:\Program Files\ODA\ODAFileConverter 27.1.0\ODAFileConverter.exe`

## 关键技术点（踩坑记录）

### 1. DWG 读取必须用 ezdxf.odafc

```python
import ezdxf
ezdxf.options.set('odafc-addon', 'win_exec_path',
                  r'C:\Program Files\ODA\ODAFileConverter 27.1.0\ODAFileConverter.exe')
from ezdxf.addons import odafc
doc = odafc.readfile(r'C:\path\to\file.dwg')  # 自动 DWG→DXF→读取
```

错误做法：`subprocess.run([ODA_EXE, src, dst, ...])` → GUI程序命令行调用不工作

### 2. 红线识别策略

**模式 A：按图层名匹配**
```python
REDLINE_KEYWORDS = ['红线', '用地红线', 'redline', 'REDLINE']
```

**模式 B：面积量算图无红线图层时**
- 过滤掉图框（TK图层）和面积<1亩的小段线
- 剩余全部作为宗地

### 3. CGCS2000 坐标识别

- 北坐标 ≈ 7位数（如 3641349.088）
- 东坐标 ≈ 8位数，前2位是带号（如 39530339.816 → 带号 39）
- 坐标方向不固定，根据数值大小自动判断 X=东/Y=北 或反之

### 4. EPSG 映射

**公式：`EPSG = 4509 + 带号`**（3度带）

⚠️ 不要用 `4520 + 带号`（6度带，偏移约300km）！

| 带号 | 中央经线 | EPSG | 典型地区 |
|------|---------|------|---------|
| 37 | 111°E | 4546 | 西安 |
| 38 | 114°E | 4547 | 武汉、北京 |
| **39** | **117°E** | **4548** | **蚌埠、合肥、济南** |
| 40 | 120°E | 4549 | 上海、青岛 |

### 5. 坐标转换去带号前缀

```python
zone_prefix = zone * 1000000  # 39 → 39000000
true_easting = east_y - zone_prefix
lon, lat = transformer.transform(true_easting, north_x)  # 先东后北
```

### 6. KML 颜色格式：AABBGGRR

| 想要颜色 | 正确写法 | 说明 |
|---------|---------|------|
| 红色边框 | `ff0000ff` | RR=ff 即红色 |
| 不填充 | `<fill>0</fill>` | 仅边框无内部蒙版 |

⚠️ `ffff0000` 是蓝色不是红色！

### 7. 户名+面积匹配（面积量算图）

CAD 中文字通常在不同图层：
- **姓名层**：户名（TEXT/MTEXT 实体）
- **MJZJ**：面积注记（TEXT 实体，格式如 "974.28平方米,合1.4614亩"）

匹配逻辑：计算每块宗地重心，找最近的文字实体。每块宗地同时匹配户名和面积。

### 8. 不要拐角标注

**不生成拐角图钉标注**——只输出红线本身，干净利落。用户反馈标注太多反而杂乱。

## 执行流程

### 步骤 1：复制 DWG 到纯英文路径

ODA File Converter 不支持中文路径：

```bash
mkdir -p /c/temp/dwg_work
cp "原始DWG路径.dwg" /c/temp/dwg_work/redline.dwg
```

### 步骤 2：分析 DWG 结构

先判断是红线图还是面积量算图：

```python
# 检查是否有红线图层
layers = set(e.dxf.layer for e in msp)
has_redline = any(kw in layer for kw in ['红线', 'redline'] for layer in layers)
has_text = any(l in ['姓名层', 'MJZJ'] for l in layers)
```

### 步骤 3：运行提取脚本

使用 bundled 脚本 `scripts/extract_redline_from_dwg.py`：

```bash
python scripts/extract_redline_from_dwg.py \
    --input /c/temp/dwg_work/redline.dwg \
    --output 输出路径/项目红线.kml \
    --project-name "项目名称"
```

脚本自动完成全部流程：读取DWG → 识别红线/宗地 → 匹配文字 → 转换坐标 → 生成KML

### 步骤 4：交付

1. 把 KML 放到用户桌面
2. 告知双击即可用谷歌地球打开
3. 提示点击地块可查看户名+面积信息（如有）

## 资源说明

- `scripts/extract_redline_from_dwg.py` — 全自动提取脚本（DWG→KML，支持两种模式）
- `scripts/cgcs2000_to_kml.py` — 备用脚本，支持 CSV 坐标输入（当自动提取失败时用）
- `references/coordinate_systems.md` — CGCS2000/高斯克吕格/EPSG 详细参考表+KML颜色速查
