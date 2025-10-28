import os
import json
import sys
import dotenv
import argparse
import langchain_core.exceptions
from langchain_openai import ChatOpenAI
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from structure import Structure  # 假设 structure.py 存在并且定义了 Structure

# --- .env ---
# 确保你的 .env 文件包含以下内容（使用你的实际值）:
# MODEL_NAME=deepseek_v31
# CUSTOM_API_KEY=你的API密钥
# ----------------

if os.path.exists('.env'):
    dotenv.load_dotenv()

# 假设 template.txt 和 system.txt 存在
try:
    template = open("template.txt", "r", encoding="utf-8").read()
    system = open("system.txt", "r", encoding="utf-8").read()
except FileNotFoundError as e:
    print(f"Error: {e}. 确保 'template.txt' 和 'system.txt' 文件存在。", file=sys.stderr)
    sys.exit(1)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, required=True, help="jsonline data file")
    return parser.parse_args()


def main():
    args = parse_args()
    
    # --- 配置 ---
    # 从 .env 文件中获取模型名称和 API 密钥
    # 你的第一个脚本使用 'deepseek_v31'
    model_name = os.environ.get("MODEL_NAME", 'deepseek_v31') 
    
    # 你需要将在 .env 文件中定义的密钥变量名（例如 CUSTOM_API_KEY）替换到下面
    # 修改：现在它会读取 'OPENAI_API_KEY'
    api_key = os.environ.get("OPENAI_API_KEY") 
    
    if not api_key:
        # 更新错误信息
        print("Error: 'OPENAI_API_KEY' not found in .env file.", file=sys.stderr)
        print("请在 .env 文件中设置 OPENAI_API_KEY=你的密钥", file=sys.stderr)
        sys.exit(1)

    # 你的第一个脚本中的 API 基地址
    # LangChain 会自动附加 /chat/completions
    custom_api_base = "https://ai-maas.wair.ac.cn/maas/v1" 
    # -------------

    data = []
    try:
        with open(args.data, "r", encoding="utf-8") as f:
            for line in f:
                data.append(json.loads(line))
    except FileNotFoundError:
        print(f"Error: 数据文件 {args.data} 未找到。", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: {args.data} 中包含无效的 JSON。", file=sys.stderr)
        sys.exit(1)

    if not data:
        print(f"警告: {args.data} 为空或无法解析。", file=sys.stderr)
        return

    seen_ids = set()
    unique_data = []
    for item in data:
        if item.get('id') not in seen_ids: # 使用 .get 避免 KeyError
            seen_ids.add(item['id'])
            unique_data.append(item)

    data = unique_data
    print(f'打开: {args.data}, 找到 {len(data)} 条唯一记录', file=sys.stderr)

    # --- 初始化 LLM ---
    # 使用你的自定义 API 基地址、API 密钥和模型名称
    llm = ChatOpenAI(
        model=model_name,
        openai_api_base=custom_api_base,
        openai_api_key=api_key
    ).with_structured_output(Structure, method="function_calling")
    # ---------------------

    print(f'连接到: {model_name} at {custom_api_base}', file=sys.stderr)
    
    prompt_template = ChatPromptTemplate.from_messages([
        SystemMessagePromptTemplate.from_template(system),
        HumanMessagePromptTemplate.from_template(template=template)
    ])

    chain = prompt_template | llm

    language = os.environ.get("LANGUAGE", 'Chinese')
    output_filename = args.data.replace('.jsonl', f'_AI_enhanced_{language}.jsonl')

    # 确保输出文件是空的（如果它已经存在），以避免附加到旧运行中
    open(output_filename, 'w').close() 

    for idx, d in enumerate(data):
        if 'summary' not in d:
            print(f"跳过 {d.get('id', '未知 ID')}: 缺少 'summary' 字段", file=sys.stderr)
            continue
            
        try:
            response: Structure = chain.invoke({
                "language": language,
                "content": d['summary']
            })
            d['AI'] = response.model_dump()
        except langchain_core.exceptions.OutputParserException as e:
            print(f"{d['id']} has an error: {e}", file=sys.stderr)
            d['AI'] = {
                "tldr": "Error",
                "motivation": "Error",
                "method": "Error",
                "result": "Error",
                "conclusion": "Error"
            }
        except Exception as e: # 捕获其他潜在的 API 错误
            print(f"{d['id']} 遇到意外错误: {e}", file=sys.stderr)
            d['AI'] = {"error": str(e)}

        with open(output_filename, "a", encoding="utf-8") as f:
             # 确保 JSON 在写入时使用 UTF-8
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

        print(f"已完成 {idx + 1}/{len(data)}", file=sys.stderr)

if __name__ == "__main__":
    # 确保 structure.py 存在
    if not os.path.exists("structure.py"):
        print("Error: 'structure.py' file not found.", file=sys.stderr)
        print("请创建 'structure.py' 并定义 'Structure' Pydantic 模型。", file=sys.stderr)
    else:
        main()

