import os
import logging

logger = logging.getLogger(__name__)

def save_attachments(uid, message, output_dir="file/pdf/"):
    """
    遍历邮件所有附件，如果是PDF则保存。
    
    :param uid: 邮件的 UID (字符串)
    :param message: email.message.EmailMessage 对象
    :param output_dir: 保存目录，默认为 file/pdf/
    :return: 成功保存的文件路径列表
    """
    # 如果目录不存在，自动创建
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        logger.info(f"创建目录: {output_dir}")
        
    saved_paths = []
    
    # 遍历邮件的所有部分寻找附件
    for part in message.iter_attachments():
        filename = part.get_filename()
        
        # 如果没有文件名，跳过
        if not filename:
            continue
            
        # 判断是否为 PDF (忽略大小写)
        if filename.lower().endswith('.pdf'):
            # 构建新的文件名
            new_filename = f"{uid}_{filename}"
            filepath = os.path.join(output_dir, new_filename)
            
            # 读取内容并保存
            payload = part.get_payload(decode=True)
            if payload:
                with open(filepath, 'wb') as f:
                    f.write(payload)
                
                logger.info(f"成功保存附件: {filepath}")
                saved_paths.append(filepath)
                
    return saved_paths
