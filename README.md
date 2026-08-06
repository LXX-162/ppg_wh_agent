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
  - [邮件处理（main.py）](#邮件处理mainpy)
  - [多维表同步（sync_orders.py）](#多维表同步sync_orderspy)
- [业务指令处理](#业务指令处理)
- [发运方式缓存（Shipping Cache）](#发运方式缓存shipping-cache)
- [暂存区（PendingOrders）](#暂存区pendingorders)
- [业务字段清洗流水线](#业务字段清洗流水线)
- [多维表字段映射](#多维表字段映射)
- [幂等性保证](#幂等性保证)

---

## 系统概述

本系统每日自动完成以下工作：

1. **拉取邮件** —— 通过 IMAP 拉取邮箱全部邮件
2. **更新发运缓存** —— 从 wenjuan / SHIPPING_INFO 邮件中提取发运方式与危险品信息，持久化到 `shipping_all.json`
3. **识别业务指令** —— 解析邮件正文，自动执行取消、改单、拆单等操作
4. **解析 PDF 发货单** —— 提取订单号、地址、重量、数量、联系人等字段
5. **规范化字段** —— 通过多级清洗流水线标准化地址、联系人、发运方式等
6. **写入暂存区** —— 新订单写入 `pending_orders.json` 暂存
7. **同步飞书多维表** —— 将暂存区订单批量写入飞书多维表，同步取消/改单等状态变更

---

## 整体架构

```
邮件 (IMAP)
    │
    ▼
main.py
    ├── 1. 更新 Shipping Cache（wenjuan / SHIPPING_INFO 邮件）
    ├── 2. 识别业务指令（取消 / 改单 / 拆单）
    └── 3. 解析 PDF_ORDER → FieldNormalizer → PendingOrdersManager

sync_orders.py
    ├── 处理 已取消 → 修改多维表状态
    ├── 处理 已更新 → 覆盖多维表记录
    ├── 写入 pending / 拆单 → 新增多维表行
    └── 输出 output/orders_YYYY-MM-DD.json
```

---

## 目录结构

```
ppg_wh_agent/
├── main.py                    # 邮件拉取 & 解析主入口
├── sync_orders.py             # 多维表写入入口
├── inspect_orders.py          # 暂存区查询工具（开发辅助）
├── requirements.txt
├── .env                       # 环境变量（密钥等，不入库）
│
├── mail/
│   ├── mail_reader.py         # IMAP 邮件拉取
│   ├── mail_filter.py         # 邮件类型识别（PDF_ORDER / SHIPPING_INFO / …）
│   └── email_saver.py         # 附件保存
│
├── parser/
│   ├── pdf_parser.py          # PDF 文本提取 + 坐标层精确单号提取
│   ├── content_parser.py      # 正文/PDF 文本字段解析
│   └── schema.py              # 字段 schema 定义
│
├── business/
│   ├── field_normalizer.py    # 业务清洗流水线总控
│   ├── rule_engine.py         # 规则引擎
│   └── normalizers/
│       ├── order_info_normalizer.py   # 日期规范化
│       ├── requirement_normalizer.py  # 客户要求清洗
│       ├── contact_normalizer.py      # 联系人清洗
│       ├── address_normalizer.py      # 地址规范化 / 收货单位匹配 / 到货省市
│       └── logistics_normalizer.py    # 发运方式 & 危险品类别
│
├── feishu/
│   └── bitable.py             # 飞书多维表 API 封装
│
├── utils/
│   ├── cache_manager.py       # CacheManager / PendingOrdersManager / OrdersManager
│   ├── seen_mails.py          # 已读邮件 UID 持久化
│   └── config.py              # 配置加载
│
├── file/                      # PDF 附件保存目录
├── output/
│   ├── orders_YYYY-MM-DD.json           # 每日排序后的待同步订单
│   └── cache/
│       ├── shipping_YYYY-MM-DD.json     # 每日发运缓存快照
│       ├── shipping_all.json            # 全量历史发运缓存（累积合并）
│       └── pending_orders.json          # 暂存区（所有状态订单）
└── WH_check/                  # 其他检查脚本（独立工具）
```

---

## 环境配置

复制并填写 `.env` 文件：

```env
# 邮件（IMAP）
MAIL_HOST=imap.feishu.cn
MAIL_PORT=993
MAIL_USER=<邮箱账号>
MAIL_PASSWORD=<邮箱密码>

# 飞书多维表
FEISHU_APP_ID=<应用 ID>
FEISHU_APP_SECRET=<应用密钥>
FEISHU_BITABLE_APP_TOKEN=<多维表 App Token>
FEISHU_BITABLE_TABLE_ID=<订单表 Table ID>
FEISHU_RECEIVER_TABLE_ID=<收货方表 Table ID>
```

安装依赖：

```bash
pip install -r requirements.txt
```

> `jionlp` 会在首次运行 `main.py` 时自动检测并安装（优先清华源，失败后尝试阿里源）。

---

## 运行说明

### 步骤一：邮件解析

```bash
python main.py
```

- 拉取邮箱全部邮件（`ALL`），自动跳过已处理 UID
- 更新发运缓存，识别并执行业务指令
- 将新 PDF 订单写入 `pending_orders.json`

### 步骤二：同步多维表

```bash
python sync_orders.py
```

- 读取 `pending_orders.json` 中所有待处理订单
- 按状态分批处理：取消 → 改单覆盖 → 新增
- 输出 `output/orders_YYYY-MM-DD.json` 并标记 `synced`

---

## 核心流程详解

### 邮件处理（main.py）

```
拉取全部邮件（最多重试 3 次）
    │
    ├─ 遍历一（不限已读）：更新 Shipping Cache
    │       ├─ wenjuan 邮件（无正文 + 有 PDF）：从标题提取发运方式，写入/覆盖缓存
    │       └─ SHIPPING_INFO 邮件：首次写入，不覆盖
    │
    ├─ 遍历二：识别业务指令
    │       ├─ 含"取消/停止/作废/不用发"→ 标记 已取消
    │       ├─ 含"更新/以此为准/重新提供"→ 解析 PDF → 标记 已更新
    │       └─ 含"拆"且附件 >= 2 个 PDF → 原单 已更新 + 子单 拆单
    │
    └─ 遍历三（跳过已读 UID）：解析 PDF_ORDER
            ├─ save_attachments → 保存 PDF 到 file/
            ├─ PDFParser.parse_pdf + extract_order_no_coord → 文本 + 坐标层单号
            ├─ ContentParser.parse_pdf_text → 原始字段 dict
            ├─ FieldNormalizer.normalize → 业务清洗
            └─ PendingOrdersManager.add_orders → 写入暂存区
```

**回复链截断**：邮件正文在送入业务指令识别前，会在"回复/转发链"起始处截断，确保指令识别仅基于新邮件内容。支持识别以下格式：
- `-----Original Message-----`
- Outlook/飞书英文转发头（`From: … Sent: …`）
- 中文转发头（`发件人: … 发送时间: …`）

---

### 多维表同步（sync_orders.py）

```
加载 pending_orders.json
    │
    ├─ 构建「单号 → record_id」映射（拉取多维表全量记录）
    │
    ├─ 已取消：batch_update_records → 仅改状态字段为"已取消"
    ├─ 已更新（多维表已有记录）：batch_update_records → 覆盖全字段
    ├─ pending / 拆单 / 已更新（无记录）：write_records → 新增行
    │
    ├─ 输出 output/orders_YYYY-MM-DD.json（按省市/地址/单号排序）
    └─ mark_synced → 更新暂存区状态为 synced
```

无法解析日期的订单自动标记为 `anomaly`，跳过本次写入。

---

## 业务指令处理

| 指令类型 | 触发关键词（新邮件正文或主题） | 处理逻辑 |
|--------|--------------------------|---------|
| **取消** | 停止、作废、不用发、取消 | 从正文（截断后）+ 主题提取单号，设 `sync_status = 已取消` |
| **改单** | 更新、以此为准、重新提供 | 解析附件 PDF，用新字段覆盖暂存区，设 `sync_status = 已更新` |
| **拆单** | 拆（正文或主题）+ 附件 ≥ 2 个 PDF | 第一个 PDF 更新原单（已更新），第二个 PDF 新增子单（拆单），子单号若与原单相同则附 `-1` 后缀 |

---

## 发运方式缓存（Shipping Cache）

- **写入规则**：
  - `wenjuan` 发送（无正文 + 有 PDF 附件）：从**标题**提取发运方式（零担/保温车/包车/自提），**覆盖**已有记录
  - 其他人的 `SHIPPING_INFO` 邮件：解析正文表格，**首次写入**，不覆盖
- **存储路径**：
  - `output/cache/shipping_YYYY-MM-DD.json`（每日快照）
  - `output/cache/shipping_all.json`（全量历史累积，merge 写入不删历史）
- **使用时机**：解析 PDF 后，若字段未能提取到发运方式/危险品，从缓存补充

---

## 暂存区（PendingOrders）

文件路径：`output/cache/pending_orders.json`

格式：`{ order_no: { ...字段..., sync_status, synced_at } }`

| `sync_status` | 含义 |
|-------------|------|
| `pending` | 尚未写入多维表 |
| `synced` | 已成功写入多维表 |
| `已更新` | 改单，待覆盖多维表已有记录 |
| `已取消` | 已取消，待修改多维表状态字段 |
| `拆单` | 拆分子单，待新增至多维表 |
| `anomaly` | 日期无法解析，异常跳过 |

**`add_orders` 合并规则**：

| 已有状态 | 新数据情况 | 结果 |
|---------|----------|------|
| 不存在 | 任意 | 新增，`pending` |
| `synced` | 内容有变化 | 覆盖，设为 `已更新` |
| `synced` | 内容无变化 | 保持不变 |
| `pending` | 任意 | 直接覆盖 |
| `anomaly` / `已取消` | 任意 | 保持不变，不覆盖 |

---

## 业务字段清洗流水线

`FieldNormalizer.normalize()` 按以下顺序执行：

```
OrderInfoNormalizer.normalize_date      # 日期规范化（→ YYYY/MM/DD）
RequirementNormalizer.normalize         # 客户要求去噪清洗
ContactNormalizer.normalize             # 联系人去噪、手机号提取
AddressNormalizer.normalize_address     # 地址规范化（精确/模糊匹配）
AddressNormalizer.normalize_receiver    # 收货单位匹配
AddressNormalizer.normalize_city        # 到货省市提取（jionlp NLP）
LogisticsNormalizer.normalize_shipping  # 发运方式标准化
LogisticsNormalizer.normalize_danger    # 危险品类别识别
```

---

## 多维表字段映射

| 飞书字段 | 来源 | 说明 |
|---------|------|------|
| 客户名 | 固定值 `"芜湖PPG"` | |
| 单号 | `order_no` | |
| 订单状态 | `sync_status` 映射 | 正常/已更新/已取消/拆单 |
| 下单日期 | `order_date` | 转为 Unix 毫秒时间戳 |
| 地址状态 | `address_exact_match` | 精确匹配/模糊匹配 |
| 收货单位 | `receiver` | |
| 收货公司名 | `company_name` | |
| 收货地址 | `address` | |
| 收货人 | `contact` | |
| 客户要求 | `requirement` | |
| 数量 | `quantity` | float |
| 重量 | `weight` | float，去 KG 后缀 |
| 发运方式 | `发运方式` | |
| 始发城市 | 固定值 `"马鞍山库"` | |
| 到货城市 | `到货城市` | |
| 到货省份 | `到货省份` | |
| 产品特性 | `危险品类别` | |

---

## 幂等性保证

- **邮件去重**：已处理 UID 持久化至 `output/cache/seen_mails.json`，重复运行自动跳过
- **订单去重**：`PendingOrdersManager.add_orders` 按 `order_no` 去重，`synced` 订单内容无变化时不覆盖
- **多维表写入**：`sync_orders.py` 每次先建立「单号 → record_id」映射，已取消/已更新走 `batch_update_records`，不产生重复行
- **发运缓存**：其他人 SHIPPING_INFO 邮件首次写入后不覆盖，防止重复运行污染数据
