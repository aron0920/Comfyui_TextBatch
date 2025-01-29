import os
import json
import logging
from server import PromptServer
import torch
import numpy as np
from typing import List, Union

# 設定基本的日誌記錄格式和級別
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TextBatchNode:
    """
    文本批次處理節點
    用於將大型文本文件按照指定分隔符分割成多個部分
    支持狀態保存和恢復，可以記住上次處理的位置
    """
    def __init__(self):
        # 初始化狀態文件路徑，用於保存處理進度
        self.state_file = os.path.join(os.path.dirname(__file__), "text_batch_state.json")
        self.state = self.load_state()
        self.reset_state()  # 添加初始化重置

    def reset_state(self):
        """重置狀態到初始值"""
        self.state = {
            "prompts": [],
            "current_index": 0,
            "last_input": "",
            "last_input_mode": "",
            "last_separator": "",
            "last_separator_type": "newline",
            "last_start_index": 0,
            "completed": False
        }
        self.save_state()

    @classmethod
    def INPUT_TYPES(cls):
        """
        定義節點的輸入參數類型和預設值
        """
        return {
            "required": {
                # 修改預設值為 text
                "input_mode": (["text", "file"], {"default": "text"}),
                # 文本文件路徑輸入
                "text_file": ("STRING", {"multiline": False, "default": "Enter the path to your text file here"}),
                # 直接輸入文本
                "input_text": ("STRING", {
                    "multiline": True, 
                    "default": "Enter your text here...",
                    "placeholder": "Enter multiple prompts, one per line"
                }),
                # 分隔符類型
                "separator_type": (["newline", "custom"], {"default": "newline"}),
                # 文本分隔符
                "separator": ("STRING", {"default": "---"}),
                # 起始索引位置
                "start_index": ("INT", {"default": 0, "min": 0, "max": 10000}),
                # 新增自動終止選項
                "auto_stop": ("BOOLEAN", {"default": True}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"}
        }

    # 定義輸出類型
    RETURN_TYPES = ("STRING", "STRING", "INT", "INT", "BOOLEAN")
    # 定義輸出名稱
    RETURN_NAMES = ("prompt", "status", "current_index", "total", "completed")
    FUNCTION = "process_text"
    CATEGORY = "TextBatch"
    OUTPUT_NODE = True  # 添加這行

    def process_text(self, input_mode, text_file, input_text, separator_type, separator, start_index, auto_stop):
        """
        處理文本文件或直接輸入文本的主要方法
        參數:
            input_mode: 輸入模式（file或text）
            text_file: 要處理的文本文件路徑
            input_text: 直接輸入的文本
            separator_type: 分隔符類型（custom或newline）
            separator: 用於分割文本的分隔符
            start_index: 開始處理的索引位置
            auto_stop: 是否自動終止
        返回:
            tuple: (提示文本, 狀態信息, 當前索引, 總數, 是否完成)
        """
        try:
            # 檔案模式的驗證
            if input_mode == "file":
                if not text_file.strip() or text_file == "Enter the path to your text file here":
                    return ("", "Error: Please provide a valid file path", -1, 0, True)
                if not os.path.exists(text_file):
                    return ("", f"Error: File not found: {text_file}", -1, 0, True)
                with open(text_file, 'r', encoding='utf-8') as file:
                    content = file.read().strip()
                if not content:
                    return ("", "Error: File is empty", -1, 0, True)
                current_input = text_file
            else:
                if not input_text.strip() or input_text == "Enter your text here...":
                    return ("", "Error: Please provide input text", -1, 0, True)
                current_input = input_text
            
            # 檢查是否需要重置
            need_reset = (
                self.state.get("last_input") != current_input or
                self.state.get("last_input_mode") != input_mode or
                self.state.get("last_separator") != separator or
                self.state.get("last_separator_type") != separator_type or
                self.state.get("completed", False)
            )

            # 如果需要重置，重新加載所有數據
            if need_reset:
                self.reset_state()
                if input_mode == "file":
                    self.load_prompts(text_file, separator_type, separator)
                else:
                    self.load_text_input(input_text, separator_type, separator)
                
                # 檢查是否成功加載了提示
                if len(self.state["prompts"]) == 0:
                    return ("", "Error: No valid prompts found", -1, 0, True)
                
                self.state.update({
                    "last_input": current_input,
                    "last_input_mode": input_mode,
                    "last_separator": separator,
                    "last_separator_type": separator_type,
                    "current_index": 0
                })

            total = len(self.state["prompts"])
            if total == 0:
                return ("", "No prompts loaded", 0, 0, True)

            # 安全獲取當前索引
            current_index = min(self.state.get("current_index", 0), total - 1)
            
            try:
                # 安全獲取當前提示
                prompt = self.state["prompts"][current_index]
            except IndexError:
                # 如果發生索引錯誤，重置到最後一個有效索引
                current_index = total - 1
                prompt = self.state["prompts"][current_index]
                self.state["current_index"] = current_index

            # 檢查是否完成
            is_last = current_index >= total - 1
            
            # 更新狀態
            if not is_last and auto_stop:
                self.state["current_index"] = current_index + 1
                completed = False
            else:
                completed = True
            
            self.state["completed"] = completed
            
            # 生成狀態信息
            status = f"Processing {current_index + 1}/{total}"
            if input_mode == "file":
                status += f" | File: {os.path.basename(text_file)}"
            if completed:
                status += " | Completed"

            # 保存狀態
            self.save_state()

            # 更新節點顯示的當前索引
            if not completed:
                PromptServer.instance.send_sync("textbatch-node-feedback", 
                    {"node_id": unique_id, "widget_name": "start_index", "type": "int", "value": self.state["current_index"]})

            return (prompt, status, current_index, total, completed)

        except Exception as e:
            logger.error(f"Error in process_text: {str(e)}")
            return ("", f"Error: {str(e)}", -1, 0, True)

    def load_prompts(self, text_file, separator_type, separator):
        """
        從文件中加載並分割提示文本
        參數:
            text_file: 文本文件路徑
            separator_type: 分隔符類型（custom或newline）
            separator: 用於分割文本的分隔符
        """
        try:
            with open(text_file, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # 根據分隔符類型選擇分割方式
            if separator_type == "newline":
                self.state["prompts"] = [prompt.strip() for prompt in content.splitlines() if prompt.strip()]
            else:
                self.state["prompts"] = [prompt.strip() for prompt in content.split(separator) if prompt.strip()]
            
            logger.info(f"Loaded {len(self.state['prompts'])} prompts from {text_file}")
        except Exception as e:
            logger.error(f"Error loading prompts: {str(e)}")
            raise

    def load_text_input(self, input_text, separator_type, separator):
        """
        處理直接輸入的文本
        參數:
            input_text: 輸入的文本
            separator_type: 分隔符類型（custom或newline）
            separator: 用於分割文本的分隔符
        """
        try:
            # 根據分隔符類型選擇分割方式
            if separator_type == "newline":
                self.state["prompts"] = [prompt.strip() for prompt in input_text.splitlines() if prompt.strip()]
            else:
                self.state["prompts"] = [prompt.strip() for prompt in input_text.split(separator) if prompt.strip()]
            
            logger.info(f"Loaded {len(self.state['prompts'])} prompts from direct input")
        except Exception as e:
            logger.error(f"Error processing input text: {str(e)}")
            raise

    def load_state(self):
        """
        從狀態文件中加載之前的處理狀態
        """
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading state file: {str(e)}")
        return {
            "prompts": [], 
            "current_index": 0, 
            "last_input": "", 
            "last_input_mode": "file",
            "last_separator": "",
            "last_separator_type": "newline",
            "last_start_index": 0,
            "completed": False  # 添加完成狀態標記
        }

    def save_state(self):
        """
        將當前處理狀態保存到狀態文件
        """
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f)
        except Exception as e:
            logger.error(f"Error saving state file: {str(e)}")

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """
        控制節點的執行頻率
        返回不同的值會觸發節點重新執行
        """
        current_index = kwargs.get("current_index", 0)
        total = kwargs.get("total", 0)
        completed = kwargs.get("completed", False)
        auto_stop = kwargs.get("auto_stop", True)
        
        # 如果啟用了自動停止且未完成，返回 float("nan") 觸發重新執行
        if auto_stop and not completed and current_index < total - 1:
            return float("nan")  # 使用 nan 確保每次都會觸發重新執行
            
        return current_index  # 返回當前索引，不會觸發重新執行

class TextSplitCounterNode:
    """
    文本分割計數節點
    用於計算分割後的文本總數
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_mode": (["file", "text"], {"default": "file"}),
                "text_file": ("STRING", {"multiline": False, "default": "Enter the path to your text file here"}),
                "input_text": ("STRING", {
                    "multiline": True,
                    "default": "Enter your text here...",
                }),
                "separator_type": (["newline", "custom"], {"default": "newline"}),
                "separator": ("STRING", {"default": "---"}),
            }
        }

    RETURN_TYPES = ("INT", "STRING",)
    RETURN_NAMES = ("count", "status")
    FUNCTION = "count_splits"
    CATEGORY = "TextBatch"

    def count_splits(self, input_mode, text_file, input_text, separator_type, separator):
        try:
            if input_mode == "file":
                if not os.path.exists(text_file):
                    return (0, f"Error: File not found: {text_file}")
                with open(text_file, 'r', encoding='utf-8') as file:
                    content = file.read()
            else:
                content = input_text

            # 根據分隔符類型計算分割數
            if separator_type == "newline":
                splits = [x.strip() for x in content.splitlines() if x.strip()]
            else:
                splits = [x.strip() for x in content.split(separator) if x.strip()]

            count = len(splits)
            status = f"Total splits: {count}"
            return (count, status)
        except Exception as e:
            logger.error(f"Error in count_splits: {str(e)}")
            return (0, f"Error: {str(e)}")

class TextQueueProcessor:
    """處理文字佇列的節點"""
    def __init__(self):
        self.state_file = os.path.join(os.path.dirname(__file__), "text_queue_processor_state.json")
        self.state = self.load_state()
        self.reset_state()

    def reset_state(self):
        """重置狀態到初始值"""
        self.state = {
            "current_index": 0,
            "last_input": "",
            "completed": False
        }
        self.save_state()

    def load_state(self):
        """從狀態文件中加載之前的處理狀態"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading state file: {str(e)}")
        return {
            "current_index": 0,
            "last_input": "",
            "completed": False
        }

    def save_state(self):
        """將當前處理狀態保存到狀態文件"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f)
        except Exception as e:
            logger.error(f"Error saving state file: {str(e)}")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "multiline": True,
                    "default": "1girl\n1cat\n1dog",
                    "placeholder": "輸入提示詞，可用分隔符或換行分割"
                }),
                "separator_type": (["newline", "custom"], {"default": "newline"}),
                "separator": ("STRING", {"default": ","}),
                "start_index": ("INT", {"default": 0, "min": 0, "max": 10000}),
                "trigger_next": ("BOOLEAN", {"default": True, "label_on": "Trigger", "label_off": "Don't trigger"}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"}
        }

    RETURN_TYPES = ("STRING", "INT", "INT", "BOOLEAN", "STRING")
    RETURN_NAMES = ("text", "current_index", "total", "completed", "status")
    FUNCTION = "process"
    CATEGORY = "TextBatch"
    OUTPUT_NODE = True

    def process(self, text, separator_type, separator, start_index, trigger_next, unique_id):
        try:
            # 檢查是否需要重置
            need_reset = (
                self.state.get("last_input") != text or
                self.state.get("completed", False)
            )

            if need_reset:
                self.reset_state()
                self.state["last_input"] = text

            # 根據分隔符類型分割文本
            if separator_type == "newline":
                lines = [line.strip() for line in text.splitlines() if line.strip()]
            else:
                lines = [line.strip() for line in text.split(separator) if line.strip()]
            
            total = len(lines)

            if total == 0:
                return ("", -1, 0, True, "No valid text found")

            # 獲取當前索引
            current_index = min(max(start_index, self.state.get("current_index", 0)), total - 1)
            
            # 獲取當前行
            current_text = lines[current_index]

            # 檢查是否是最後一行
            is_last = current_index >= total - 1
            
            # 更新狀態
            if not is_last and trigger_next:
                self.state["current_index"] = current_index + 1
                completed = False
                # 使用自己的事件名稱
                PromptServer.instance.send_sync("textbatch-add-queue", {})
            else:
                completed = True
                self.state["current_index"] = 0

            self.state["completed"] = completed
            self.save_state()

            # 生成狀態信息
            status = f"Processing {current_index + 1}/{total}"
            if completed:
                status += " | Completed"

            # 更新節點顯示的當前索引
            if not completed:
                PromptServer.instance.send_sync("textbatch-node-feedback", 
                    {"node_id": unique_id, "widget_name": "start_index", "type": "int", "value": self.state["current_index"]})

            return (current_text, current_index, total, completed, status)

        except Exception as e:
            logger.error(f"Error in process: {str(e)}")
            return ("", -1, 0, True, f"Error: {str(e)}")

# 節點類映射
NODE_CLASS_MAPPINGS = {
    "TextBatch": TextBatchNode, 
    "TextQueueProcessor": TextQueueProcessor,
    "TextSplitCounter": TextSplitCounterNode
}

# 節點顯示名稱映射
NODE_DISPLAY_NAME_MAPPINGS = {
    "TextBatch": "Text Batch", 
    "TextQueueProcessor": "Text Queue Processor",
    "TextSplitCounter": "Text Split Counter"
}