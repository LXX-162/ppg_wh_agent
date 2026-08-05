# pyrefly: ignore [missing-import]
import pdfplumber
import re
import logging

logger = logging.getLogger(__name__)

class PDFParser:
    @staticmethod
    def parse_pdf(file_path: str) -> str:
        """
        提取 PDF 所有文字，按页面顺序拼接为字符串。
        如果当前页面包含 "总毛重"，则停止继续读取后面的页面。
        """
        text_content = []
        
        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_num = i + 1
                    logger.info(f"读取第 {page_num} 页: {file_path}")
                    
                    text = page.extract_text()
                    
                    # 避免空页
                    if not text:
                        continue
                        
                    text_content.append(text)
                    
                    # 停止条件
                    if "总毛重" in text:
                        logger.info(f"在第 {page_num} 页检测到 '总毛重'，停止读取后续页面。")
                        break
                        
            return "\n".join(text_content)
            
        except Exception as e:
            logger.error(f"解析 PDF 出错 {file_path}: {e}")
            return ""

    @staticmethod
    def extract_order_no_coord(file_path: str) -> str:
        """
        从 PDF 的【字符坐标层】精确提取"发货单号"区域的连续 8 位订单号。

        背景：
          pdfplumber 的 extract_text() 会按"行合并容差"把不同 y 层、不同 x 列的字符合并到
          同一条文本行，导致：
            - 发货单号上方一层图形/字形（如 "Í+ÆÆ\\6Î"，top 略高）被粘进单号文本；
            - 靠近但不同 x 列的内容（如客户联系人列的手机号尾号）也可能被混入。
          即便如此，真正的订单号在 PDF 内部始终以一段"连续完整的 11 开头 8 位数字"、
          位于"发货单号"标签右下、同一 x 带内。

        本方法用 page.chars（逐字符坐标）精确定位：找到"发货单号"标签后，只在其
        正下方、x 带接近的字符中扫描连续数字，从而：
            - 不把标签上方的图形噪声（top 更小）算进去；
            - 不把左侧其他列的数字（如手机号 13511688566 的尾号）误当单号。

        :param file_path: PDF 文件路径
        :return: 权威订单号字符串；找不到时返回 ""（调用方再走文件名/文本兜底）。
        """
        try:
            with pdfplumber.open(file_path) as pdf:
                page = pdf.pages[0]
                chars = page.chars

                # ── 1. 定位 "发货单号" 四字序列（横向连续、同一 top 行）──
                label = None
                for c in chars:
                    if c.get('text') != '发':
                        continue
                    seq = [(c['top'], c['x0'], c['x1'])]
                    cur_x1 = c['x1']
                    ok = True
                    for want in ('货', '单', '号'):
                        nxt = [
                            d for d in chars
                            if d.get('text') == want
                            and abs(d['top'] - c['top']) < 3
                            and cur_x1 - 1 <= d['x0'] < cur_x1 + 12
                        ]
                        if not nxt:
                            ok = False
                            break
                        nxt = min(nxt, key=lambda d: d['x0'])
                        seq.append((nxt['top'], nxt['x0'], nxt['x1']))
                        cur_x1 = nxt['x1']
                    if ok:
                        label = (seq[0][0], seq[0][1], seq[-1][2])  # top, x0(label start), x1(label end)
                        break

                if not label:
                    return ""

                label_top, label_x0, label_x1 = label

                # ── 2. 在标签下方、x 带接近的字符中扫描连续订单号 ──
                best = None
                for c in chars:
                    if not c.get('text').isdigit():
                        continue
                    # 必须位于标签正下方一行左右（排除上方图形噪声）
                    if not (label_top + 1 <= c['top'] <= label_top + 14):
                        continue
                    # 排除明显在标签左侧的其他列数字（如客户联系人手机号）
                    if c['x0'] < label_x0 - 2:
                        continue

                    # 汇集同一水平行、x 连续的数字字符
                    row = [c]
                    col = c
                    while True:
                        nxt = [
                            d for d in chars
                            if d.get('text').isdigit()
                            and abs(d['top'] - c['top']) < 2
                            and col['x1'] - 1 <= d['x0'] < col['x1'] + 9
                        ]
                        if not nxt:
                            break
                        nxt = min(nxt, key=lambda d: d['x0'])
                        row.append(nxt)
                        col = nxt
                    row.sort(key=lambda d: d['x0'])
                    num_str = ''.join(d.get('text') for d in row)

                    m = re.search(r'(11\d{6,})', num_str)
                    if m:
                        candidate = m.group(1)
                        if len(candidate) >= 8:
                            # 优先返回恰好 8 位的连续号
                            if len(candidate) == 8:
                                return candidate
                            if best is None or len(candidate) > len(best):
                                best = candidate

                return best if best else ""

        except Exception as e:
            logger.error(f"解析 PDF 坐标单号出错 {file_path}: {e}")
            return ""
