"""
工具函數模組
包含各種通用的輔助函數
"""

def get_file_extension(filename: str) -> str:
    """
    獲取檔案副檔名
    """
    return os.path.splitext(filename)[1].lower()

def is_image_file(filename: str) -> bool:
    """
    檢查檔案是否為圖片
    """
    valid_extensions = ['.jpg', '.jpeg', '.png', '.webp']
    return any(filename.lower().endswith(ext) for ext in valid_extensions)

# 可以根據需要添加更多工具函數 