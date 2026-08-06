# PPG芜湖工业漆 - 订单比对工具

## 项目概述

PPG芜湖工业漆（马鞍山库）的订单数据比对工具集。用于交叉验证**调度台账**与**系统数据**（自动接单表）之间的一致性，快速定位差异订单。

---

## 项目结构

```
D:\project\WH_check\
├── compare.py              # JSON  vs 台账  比对（原版）
├── compare_csv.py          # CSV   vs 台账  比对（总接单表）
├── compare_csv2.py         # CSV   vs 台账  比对（副本_总接单表）
├── compare_csv2csv.py      # CSV   vs CSV   两个CSV互相比对
├── _write.py               # 辅助模块（未完成）
├── file/
│   ├── 调度台账 2023年6月.xlsx                        # 台账文件（Excel）
│   ├── 自动接单表_PPG 芜湖(工业漆)_总接单表.csv       # 自动接单表（CSV）
│   └── 自动接单表_PPG 芜湖(工业漆) 副本_总接单表.csv  # 自动接单表副本（CSV）
├── 差异报告_*.xlsx           # compare.py 生成的差异报告
├── CSV差异报告_*.xlsx        # compare_csv.py / compare_csv2.py 生成的差异报告
├── CSV2CSV差异报告_*.xlsx    # compare_csv2csv.py 生成的差异报告
└── README.md               # 本文件
```

---

## 四个脚本的区别（重点）

四个脚本共享同一套比对逻辑（字段清洗、日期解析、每日统计、差异详情、Excel高亮），
**唯一区别在于“对比的两边数据源是谁”**：

| 脚本 | 第一侧（数据源A） | 第二侧（基准B） | 用途 |
|---|---|---|---|
| **compare.py** | **系统API返回的 JSON**（`pending_orders.json`） | **Excel 台账** | 校验系统实时数据是否与台账一致 |
| **compare_csv.py** | **自动接单表 CSV**（总接单表） | **Excel 台账** | 校验导出的总接单表CSV是否与台账一致 |
| **compare_csv2.py** | **自动接单表 CSV**（副本_总接单表） | **Excel 台账** | 校验导出的副本CSV是否与台账一致 |
| **compare_csv2csv.py** | **自动接单表 CSV**（总接单表） | **自动接单表 CSV**（副本_总接单表） | 校验两份CSV导出结果是否彼此一致 |

### 对比关系图示

```
               JSON（系统API）
                    │
         compare.py │        compare_csv.py         compare_csv2.py
                    ▼              │                        │
        ┌────────Excel 台账 ◄───────┴───────────────────────┤
        │                                                    │
        │                                           compare_csv2csv.py
        ▼                                                    │
    自动接单表CSV（总接单表） ◄────── 自动接单表CSV（副本_总接单表）
```

### 关键差异点

- **compare.py（JSON侧）**
  - 数据源为系统返回的 JSON 文件（默认路径 `D:\project\ppg_wh_agent\output\cache\pending_orders.json`）。
  - JSON 侧通过 `危险品类别` 字段映射到 `产品特性`；CSV 侧直接读取 CSV 的 `产品特性` 列。
  - 生成的报告文件名前缀为 `差异报告`。

- **compare_csv.py 与 compare_csv2.py（CSV vs 台账）**
  - 代码逻辑**完全相同**，只是默认读取的 CSV 文件不同：
    - `compare_csv.py` → `自动接单表_PPG 芜湖(工业漆)_总接单表.csv`
    - `compare_csv2.py` → `自动接单表_PPG 芜湖(工业漆) 副本_总接单表.csv`
  - 两脚本都按 `始发城市 == '马鞍山库'` 过滤 CSV 与台账。
  - 生成的报告文件名前缀为 `CSV差异报告`。

- **compare_csv2csv.py（CSV vs CSV）**
  - 不涉及 Excel 台账，直接比较两份格式相同的 CSV。
  - 两侧都是 CSV，因此报告中分别用 `CSV_xx` 与 `CSV2_xx` 表示两列原值，`差异_xx` 标记结果。
  - 生成的报告文件名前缀为 `CSV2CSV差异报告`。

---

## 数据源说明

| 文件 | 说明 |
|---|---|
| **调度台账** (`调度台账 2023年6月.xlsx`) | 仓库手工维护的Excel台账，记录每日发货订单 |
| **自动接单表CSV** (`自动接单表_PPG 芜湖(工业漆)_总接单表.csv`) | 系统自动生成的接单数据（从JSON写入多维表后导出） |
| **自动接单表CSV** (`自动接单表_PPG 芜湖(工业漆) 副本_总接单表.csv`) | 总接单表的副本/备份，用于核对导出是否一致 |

比对时以台账中的 **马鞍山库** 订单为基准，筛选 `始发城市 == '马鞍山库'` 的数据进行比对。

---

## 使用方法

### 1. JSON vs 台账 比对

```powershell
cd D:\project\WH_check
python compare.py
```

- 数据源：`pending_orders.json`（默认路径 `D:\project\ppg_wh_agent\output\cache\`）
- 比对对象：**系统API返回的JSON** ↔ **Excel台账**

### 2. CSV(总接单表) vs 台账 比对

```powershell
cd D:\project\WH_check
python compare_csv.py
```

- 数据源：`自动接单表_PPG 芜湖(工业漆)_总接单表.csv`
- 比对对象：**自动接单表CSV** ↔ **Excel台账**

### 3. CSV(副本) vs 台账 比对

```powershell
cd D:\project\WH_check
python compare_csv2.py
```

- 数据源：`自动接单表_PPG 芜湖(工业漆) 副本_总接单表.csv`
- 比对对象：**副本CSV** ↔ **Excel台账**

### 4. 两个CSV互相比对

```powershell
cd D:\project\WH_check
python compare_csv2csv.py
```

- 数据源：`自动接单表_PPG 芜湖(工业漆)_总接单表.csv` 与 `自动接单表_PPG 芜湖(工业漆) 副本_总接单表.csv`
- 比对对象：**总接单表CSV** ↔ **副本CSV**

### 运行流程

1. 运行脚本后，会提示输入 **日期范围**（默认年份为2026年）
2. 支持格式：
   - 单日：`7.24` 或 `7/24`
   - 范围：`7.22-7.26` 或 `07/22-07/26`
   - 回车：比对全部日期
   - 输入 `q`：退出
3. 如果Excel台账中有多个子表，会自动选择包含"PPG工业漆"的子表，否则手动选择
4. 脚本自动筛选 **马鞍山库** 的订单，按日期分组统计并逐字段比对
5. 输出Excel差异报告

---

## 比对字段

四个脚本比对的业务字段完全一致：

| 字段 | 说明 | 比对规则 |
|---|---|---|
| 单号 | 订单唯一编号 | 用于匹配两个数据源中的同一订单 |
| 下单日期 | 订单创建日期 | 用于按天分组统计 |
| 收货单位 | 收货方名称 | `clean_text` 清洗后比对 |
| 收货地址 | 详细收货地址 | `clean_text` 清洗后比对 |
| 收货人 | 收货联系人 | `clean_text` 清洗后比对 |
| 客户要求 | 客户特殊要求 | `clean_text` 清洗后比对 |
| 数量 | 发货数量（件/桶） | 提取数字后比对 |
| 重量 | 发货重量（kg） | 提取数字后比对 |
| 发运方式 | 运输方式 | `clean_text` 清洗后比对 |
| 到货城市 | 目的地城市 | `clean_text` 清洗后比对 |
| 到货省份 | 目的地省份 | `clean_text` 清洗后比对 |
| 产品特性 | DG/NDG（危险品/非危险品） | `clean_text` 清洗后比对 |

> **注**：`compare.py` 中的 `产品特性` 字段从JSON的 `危险品类别` 字段读取；另外三个脚本直接从CSV的 `产品特性` 列读取。

---

## 输出文件

### 文件名格式

| 脚本 | 格式 |
|---|---|
| `compare.py` | `差异报告_YYYY-MM-DD_至_YYYY-MM-DD.xlsx` |
| `compare_csv.py` | `CSV差异报告_YYYY-MM-DD_至_YYYY-MM-DD.xlsx` |
| `compare_csv2.py` | `CSV差异报告_YYYY-MM-DD_至_YYYY-MM-DD.xlsx` |
| `compare_csv2csv.py` | `CSV2CSV差异报告_YYYY-MM-DD_至_YYYY-MM-DD.xlsx` |

### Excel子表

#### 子表1：每日统计

按天汇总对比结果，包含：
- 台账数量 / CSV（JSON）数量
- 共同数量（两边都有的订单）
- 差异数量（字段不一致的订单）
- 台账多出/CSV多出的订单号
- 差异订单号
- 末尾有 **合计行**

#### 子表2：差异详情

逐订单逐字段展示差异：
- **绿色 ✓**：字段一致
- **红色 ✗**：字段不一致（红底白字高亮）
- 差异字段所在行整行用黄色标记
- 末尾有 **差异统计行**（各字段的差异处数）

---

## 字段清洗规则

`clean_text()` 函数在比对前对文本做以下处理：

1. 去除所有空白字符（空格、换行等）
2. 去除括号内内容 `（中文括号）` 和 `(英文括号)`
3. 去除连字符 `-`
4. 统一全角标点为半角（逗号、句号、顿号、分号、冒号）
5. 首尾去空格

---

## 依赖库

```bash
pip install pandas openpyxl python-dateutil
```

- `pandas` — 数据处理与Excel读写
- `openpyxl` — Excel样式高亮（条件格式）
- `python-dateutil` — 灵活的日期解析
