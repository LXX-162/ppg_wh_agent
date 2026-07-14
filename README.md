# PPG WH Agent

这是一个用于从公共邮箱提取邮件正文、主题和附件 PDF，并进行解析和汇总的自动化框架。
后续，该项目提取的文本数据将可作为飞书智能体 Skill 的输入进行语义解析，并将最终结果同步至飞书多维表。

## 目录结构
见项目内的模块和文件划分。

## 快速开始

1. 复制环境变量文件
```bash
cp .env.example .env
```
2. 安装依赖
```bash
pip install -r requirements.txt
```
3. 运行主程序
```bash
python main.py
```
