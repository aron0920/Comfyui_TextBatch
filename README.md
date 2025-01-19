# Comfyui_TextBatch_aidec
可以將Text每行分割成一組，批量執行(未完成，有明顯bug待修正中)
Text Queue Processor
目前來說第一次執行可能會只執行一筆，等它執行完再跑第二次就正常，每次執行完要將start_index手動重置
有時會出現奇怪的異常，例如：一次添加多個queue，但有時又很正常，目前還在排查中可能的原因

###安裝方式：
到 ComfyUI\custom_nodes
用git clone https://github.com/aidec/Comfyui_TextBatch_aidec.git
啟動comfyUI

###使用方式：

添加 Text Queue Processor 節點
輸入Text每行一組
將text拉到想要的地方，例如：正向提示詞(Clip)

