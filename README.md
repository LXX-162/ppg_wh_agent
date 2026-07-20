# PPG WH Agent

> 自动化邮件解析与飞书多维表同步系统，专用于 PPG 芜湖仓库的每日发运订单处理。

---

## 目录

- [系统概述](#系统概述)
- [整体架构](#整体架构)
- [目录结构](#目录结构)
- [环境配置](#环境配置)
- [运行说明](#运行说明)
- [核心流程详解](#核心流程详解)
  - [邮件处理（main.py）](#邮件处理)
  - [多维表同步（sync_orders.py）](#多维表同步)
- [字段解析与清洗规则](#字段解析与清洗规则)
  - [地址规范化](#地址规范化)
  - [收货单位匹配](#收货单位匹配)
  - [到货省市提取](#到货省市提取)
  - [联系人提取](#联系人提取)
  - [发运方式与危险品类别](#发运方式与危险品类别)
- [数据文件说明](#数据文件说明)
- [多维表字段映射](#多维表字段映射)
- [幂等性保证](#幂等性保证)

---

## 系统概述

本系统从飞书邮箱（IMAP）中实时读取 PPG 发运相关邮件，解析 PDF 发货单并提取结构化订单数据，最终通过飞书 Aily 定时触发将当日订单按省市排序后批量写入飞书多维表。

**核心特性：**

- 邮件处理与多维表写入完全分离，互不依赖
- 基于 UID 的已读记录，防止重复解析
- 订单按业务日期分类管理（今天/未来/历史异常）
- 地址、收货单位、省市等字段全自动提取与清洗
- 收货单位通过飞书多维表精确匹配，支持模糊兜底
- 多维表写入幂等（先删后写），支持 Aily 重试

---

## 整体架构

```
┌─────────────────────────────────┐     ┌──────────────────────────────────────┐
│  main.py                        │     │  sync_orders.py                      │
│  （邮件处理，随时可运行）          │     │  （多维表写入，飞书 Aily 定时触发）     │
│                                 │     │                                      │
│  1. 取未读邮件 (seen_mails.json) │     │  1. 加载 pending_orders.json         │
│  2. 更新 shipping 缓存           │     │  2. 按业务日期过滤：今天/未来/异常     │
│  3. 解析 PDF → 结构化订单字段     │────▶│  3. 按省份→城市→地址排序              │
│  4. 合并写入 pending_orders.json │     │  4. 先删除今日多维表数据              │
│  5. 标记已读 UID                 │     │  5. 批量写入新数据                    │
└─────────────────────────────────┘     │  6. 更新写入状态 (synced/anomaly)    │
                                        └──────────────────────────────────────┘
```

### 数据状态流转

```
邮件 ──解析──▶ pending ──今天──▶ synced
                   │
                   ├── 未来日期 ──▶ 继续 pending（等待）
                   └── 历史日期 ──▶ anomaly（告警跳过）
```

---

## 目录结构

```
ppg_wh_agent/
├── main.py                     # 邮件处理入口（随时可运行）
├── sync_orders.py              # 多维表写入入口（Aily 触发）
├── requirements.txt
├── .env                        # 飞书/邮箱凭证（不入 git）
│
├── mail/                       # 邮件读取层
│   ├── mail_reader.py          # IMAP 连接与邮件拉取（返回带 UID 的邮件列表）
│   ├── mail_filter.py          # 邮件分类（SHIPPING_INFO / PDF_ORDER / UNKNOWN）
│   └── email_saver.py          # PDF 附件保存
│
├── parser/                     # 解析层（忠于原文，不做业务判断）
│   ├── pdf_parser.py           # PDF 文本提取（pdfplumber）
│   ├── content_parser.py       # 字段初步提取（订单号/地址/联系人/要求/重量/数量）
│   └── schema.py               # 字段结构定义
│
├── business/                   # 业务规则层
│   ├── field_normalizer.py     # 清洗流水线总控（按顺序调用各 Normalizer）
│   └── normalizers/
│       ├── address_normalizer.py     # 地址清洗、收货单位匹配、省市提取
│       ├── contact_normalizer.py     # 联系人/电话提取
│       ├── logistics_normalizer.py   # 发运方式、危险品类别
│       ├── requirement_normalizer.py # 客户要求文本清洗
│       └── order_info_normalizer.py  # 日期等基础信息规范化
│
├── feishu/
│   └── bitable.py              # 飞书多维表 API（读/写/按日期删除）
│
├── utils/
│   ├── cache_manager.py        # CacheManager（shipping 缓存）
│   │                           # OrdersManager（按日期存订单）
│   │                           # PendingOrdersManager（暂存区，含状态管理）
│   ├── seen_mails.py           # 已读邮件 UID 记录
│   └── config.py               # 配置加载
│
├── output/
│   ├── cache/
│   │   ├── pending_orders.json       # 订单暂存区（核心数据文件）
│   │   ├── seen_mails.json           # 已读邮件 UID
│   │   ├── shipping_YYYY-MM-DD.json  # 每日 shipping 缓存
│   │   └── shipping_all.json         # 全量累积 shipping 缓存
│   └── orders_YYYY-MM-DD.json        # 每日订单存档（可选）
│
└── file/
    └── pdf_test_run/           # 保存的 PDF 附件（按 UID 前缀命名）
```

---

## 环境配置

复制 `.env.example`（若有）或创建 `.env` 文件：

```env
# 邮箱配置（飞书 IMAP）
MAIL_HOST=imap.feishu.cn
MAIL_PORT=993
MAIL_USER=your-email@company.com
MAIL_PASSWORD=your-password

# 飞书开放平台（应用凭证）
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 多维表配置
FEISHU_BITABLE_APP_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx    # 多维表所在文档的 token
FEISHU_BITABLE_TABLE_ID=tblxxxxxxxxxxxxxxxxxx        # 订单主表 ID
FEISHU_RECEIVER_TABLE_ID=tblxxxxxxxxxxxxxxxxxx       # 收货单位映射表 ID
```

安装依赖：

```bash
pip install -r requirements.txt
pip install jionlp -i https://pypi.tuna.tsinghua.edu.cn/simple   # 省市识别
```

---

## 运行说明

### 邮件处理（随时可运行）

```bash
python main.py
```

- 拉取最近 50 封邮件
- 跳过已读邮件（`seen_mails.json`）
- 解析新邮件中的 PDF 发货单
- 将订单写入 `pending_orders.json`

### 多维表同步（由飞书 Aily 定时触发）

```bash
python sync_orders.py
```

- 读取 `pending_orders.json` 中所有 `pending` 状态的订单
- 过滤出业务日期 == 今天的订单
- 按**省份 → 城市 → 收货地址**排序
- 删除多维表中今天的旧数据，写入新数据
- 更新订单状态为 `synced`

---

## 核心流程详解

### 邮件处理

#### 邮件分类（`mail_filter.py`）

| 类型 | 识别规则 |
|---|---|
| `SHIPPING_INFO` | 主题含"发运"/"Shipping"等关键词，正文为表格 |
| `PDF_ORDER` | 含 `.pdf` 附件且为发货单格式 |
| `UNKNOWN` | 其他，直接跳过 |

#### 已读记录（`seen_mails.py`）

基于 IMAP UID（全局唯一）记录已处理邮件，持久化至 `output/cache/seen_mails.json`：

```json
{
    "seen_uids": ["10001", "10002", "10003"]
}
```

#### Shipping 缓存更新

`SHIPPING_INFO` 邮件（发运清单）中包含每个订单的发运方式（零担/包车/保温车/自提）和危险品类别（DG/NDG）。解析后写入：
- `output/cache/shipping_YYYY-MM-DD.json`（当日缓存）
- `output/cache/shipping_all.json`（全量累积，供跨日期查询）

### 多维表同步

#### 业务日期过滤

| 业务日期 vs 今天 | 处理方式 |
|---|---|
| `== 今天` | 写入多维表 |
| `> 今天` | 继续 pending，等日期到了再处理 |
| `< 今天` | 标记 `anomaly`，记录告警日志，跳过 |

#### 幂等保证

每次触发时：
1. 先通过 `delete_records_by_date` 删除多维表中今天的所有旧记录
2. 再写入新的完整数据集

无论 Aily 重试多少次，结果一致。

---

## 字段解析与清洗规则

### 地址规范化

**优先级（从高到低）：**

1. **特殊硬映射**：若订单内容含 `恒基达鑫` 或（`化工五路` + `武汉`），直接映射为：
   ```
   湖北省武汉市洪山区化工五路1号武汉恒基达鑫国际化工仓储有限公司
   ```

2. **从客户要求中提取**：使用正则匹配 `省/市/自治区/开发区/...` 开头的地址字符串。提取的地址严格以省/市级别为起点（不含前置公司名）。

3. **从原始地址字段提取**：剔除英文、订单号、电话、PPG 公司名等干扰后，用精准正则提取核心中文地址。
   - 特殊处理：若地址前有括号括起的附属信息（如 `(麦尔总部)`），该括号内容会与地址一同保留。

4. **兜底**：无法用正则定位时，直接使用清理后的完整文本。

**地址结尾识别词（保证"交叉口"等细节完整）：**
`号、公司、集团、厂、仓库、基地、中心、车间、工业园、园区、区、东/南/西/北/侧、路、街、道、弄、口、楼、门、栋、座、室`

### 收货单位匹配

收货单位映射表从飞书多维表（`FEISHU_RECEIVER_TABLE_ID`）实时拉取并内存缓存。

**匹配优先级：**

| 优先级 | 方法 | `address_exact_match` 值 |
|---|---|---|
| 1 | 规范化地址与多维表记录**精确匹配** | `Y`（唯一匹配）/ `Q`（多条相同地址） |
| 2 | 精确匹配命中多条时，按收货单位名称在邮件文本中的出现频率/同义词评分选最优 | `Q` |
| 3 | 精确匹配无结果，用**动态规划可分词匹配**（地址可被拆分为均在文本池中出现的子串）| `N` |
| 4 | 所有匹配失败，对全库按**字符重合度评分**取最高分兜底（永不留空）| `N` |

**`address_exact_match` 字段含义：**

| 值 | 含义 |
|---|---|
| `Y` | 地址在多维表中有唯一精确匹配 |
| `Q` | 地址匹配到多条记录，通过评分选出最优（需人工复核） |
| `N` | 无精确匹配，使用模糊推断 |

### 到货省市提取

使用 `jionlp` 库对规范化后的收货地址进行解析，自动推断省份（即使地址中只有城市名）：

- 直辖市（北京/天津/上海/重庆）的省份和城市统一设为市名
- 海南省直辖县级：若无明确市，使用区县名作为城市

输出字段：`到货省份`（如 `广东省`）、`到货城市`（如 `茂名市`）

### 联系人提取

从多个来源提取联系人和电话：

- 客户要求文本中的"收货联系人"、"收件人"等关键词后的人名+电话
- 原始地址字段中的电话号码
- 支持手机号（11位）和固话（含区号）

### 发运方式与危险品类别

从 `SHIPPING_INFO` 邮件（发运清单）中解析，以 `shipping_all.json` 为查询源：

| 字段 | 可选值 |
|---|---|
| `发运方式` | 零担 / 包车 / 保温车 / 自提 |
| `危险品类别` | DG / NDG |

---

## 数据文件说明

### `output/cache/pending_orders.json`

订单暂存区，格式：

```json
{
    "11965774": {
        "order_no": "11965774",
        "order_date": "2026/7/14",
        "address": "湖北省孝感市孝南区东山头工业园区沦河二路88号",
        "contact": "丁舒/物流部 13227183073",
        "requirement": "...",
        "weight": "368.600KG",
        "quantity": "16",
        "receiver": "孝感华楷",
        "address_exact_match": "Q",
        "到货省份": "湖北省",
        "到货城市": "孝感市",
        "发运方式": "零担",
        "危险品类别": "DG",
        "sync_status": "pending",
        "synced_at": null
    }
}
```

`sync_status` 取值：

| 值 | 含义 |
|---|---|
| `pending` | 尚未写入多维表 |
| `synced` | 已成功写入多维表，`synced_at` 记录写入时间 |
| `anomaly` | 业务日期早于今天，异常跳过 |

---

## 多维表字段映射

| 多维表字段 | 来源 | 说明 |
|---|---|---|
| 客户名 | 固定值 | `芜湖PPG` |
| 单号 | `order_no` | 从 PDF 文件名提取 |
| 订单状态 | 固定值 | `正常` |
| 下单日期 | `order_date` | 转换为 Unix 毫秒时间戳 |
| 地址状态 | `address_exact_match` | Y / Q / N |
| 收货单位 | `receiver` | 多维表收货单位映射匹配结果 |
| 收货地址 | `address` | 规范化后的中文地址 |
| 收货人 | `contact` | 联系人姓名和电话 |
| 客户要求 | `requirement` | 原文，最长约 600 字符 |
| 数量 | `quantity` | 整数 |
| 重量 | `weight` | 浮点数，单位 KG |
| 发运方式 | `发运方式` | 零担/包车/保温车/自提 |
| 始发城市 | 固定值 | `马鞍山库` |
| 到货城市 | `到货城市` | jionlp 自动识别 |
| 到货省份 | `到货省份` | jionlp 自动识别 |
| 产品特性 | `危险品类别` | DG / NDG |

---

## 幂等性保证

| 场景 | 保证机制 |
|---|---|
| 同一邮件被拉取多次 | `seen_mails.json` 基于 IMAP UID 去重 |
| 同一订单在多封邮件中出现 | `pending_orders.json` 按 `order_no` 去重 |
| 订单内容有更新（重发） | `add_orders()` 检测到内容变化后重置 `sync_status = pending`，下次 sync 重写 |
| Aily 同天多次触发 | `sync_orders.py` 先删除多维表今日数据，再全量写入 |
| 部分写入失败 | 只有全部成功才标记 `synced`，失败时保持 `pending`，下次重试 |
