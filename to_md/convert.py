import json
import argparse
import os
from itertools import count
import urllib.parse # 新增：用于URL编码

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, help="Path to the jsonline file")
    args = parser.parse_args()
    data = []
    preference = os.environ.get('CATEGORIES', 'cs.CV, cs.CL').split(',')
    preference = list(map(lambda x: x.strip(), preference))

    def rank(cate):
        if cate in preference:
            return preference.index(cate)
        else:
            return len(preference)

    try:
        with open(args.data, "r", encoding="utf-8") as f: # 建议添加 encoding="utf-8"
            for line in f:
                data.append(json.loads(line))
    except FileNotFoundError:
        print(f"错误: 输入数据文件 {args.data} 未找到。")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"错误: 解析JSON文件 {args.data} 出错: {e}")
        exit(1)


    # 尝试读取 Markdown 模板文件
    try:
        with open("paper_template.md", "r", encoding="utf-8") as f_template: # 建议添加 encoding="utf-8"
            template_content = f_template.read()
    except FileNotFoundError:
        print("错误: paper_template.md 文件未找到。")
        print("请确保该文件存在，并且已按照说明包含了 '{assistant_link_markdown}' 占位符。")
        exit(1)

    # 提取并排序类别
    # 先获取所有条目中的主要类别，确保 cnt 的 key 完整性
    all_primary_categories = set()
    for item in data:
        categories_list = item.get("categories")
        if categories_list and isinstance(categories_list, list) and len(categories_list) > 0:
            all_primary_categories.add(categories_list[0])
        # 如果不符合上述条件，该条目可能没有有效的主要类别，后续可以考虑如何处理

    sorted_categories = sorted(list(all_primary_categories), key=rank) # 使用排序后的列表

    # 统计各类别下的条目数量
    cnt = {cate: 0 for cate in sorted_categories} # 基于实际存在并排序后的类别初始化计数器
    for item in data:
        item_categories = item.get("categories", [])
        if item_categories and item_categories[0] in cnt:
            cnt[item_categories[0]] += 1

    # 生成Markdown目录
    markdown = f"<div id=toc></div>\n\n# Table of Contents\n\n"
    for cate_toc in sorted_categories: # 使用排序后的类别列表
        if cnt.get(cate_toc, 0) > 0: # 只显示有条目的类别
            markdown += f"- [{cate_toc}](#{cate_toc}) [Total: {cnt[cate_toc]}]\n"

    # 生成各类别下的Markdown内容
    item_idx_counter = count(1)
    for cate in sorted_categories:
        if cnt.get(cate, 0) == 0: # 如果类别下没有条目，则跳过
            continue

        markdown += f"\n\n<div id='{cate}'></div>\n\n"
        markdown += f"# {cate} [[Back]](#toc)\n\n"
        
        formatted_items_for_category = []
        for item in data:
            item_main_category_list = item.get("categories", [])
            if not item_main_category_list or item_main_category_list[0] != cate:
                continue

            item_title = item.get("title", "N/A")
            item_url = item.get('abs', '') # arXiv abstract URL
            
            paper_id = ""
            if item_url and 'arxiv.org/abs/' in item_url: # 确保是arXiv链接并提取ID
                paper_id = item_url.split('/')[-1]
            elif item_url: # 对于其他URL，也尝试提取最后一部分作为ID
                paper_id = item_url.split('/')[-1]
            
            # URL编码，用于构建Kimi链接的查询参数
            encoded_title = urllib.parse.quote_plus(item_title)
            encoded_item_url = urllib.parse.quote_plus(item_url)
            encoded_paper_id = urllib.parse.quote_plus(paper_id)

            # 构建 prefill_prompt 字符串
            prefill_prompt_parts = []
            if item_title != "N/A":
                prefill_prompt_parts.append(f"我们要讨论的论文是{encoded_title}")
            if item_url:
                prefill_prompt_parts.append(f"链接是{encoded_item_url}")
            if paper_id: # 只有当paper_id有效时才添加FAQ链接
                 prefill_prompt_parts.append(f"已有的FAQ链接是https://papers.cool/arxiv/kimi?paper={encoded_paper_id}")
            
            prefill_prompt_string = "，".join(prefill_prompt_parts)
            
            # 构建完整的Kimi助手URL
            assistant_url = f"https://kimi.moonshot.cn/_prefill_chat?prefill_prompt={prefill_prompt_string}&send_immediately=true&force_search=false"
            # 创建Markdown格式的链接
            assistant_link_markdown = f"[Discuss with Kimi]({assistant_url})"

            current_item_idx = next(item_idx_counter)
            
            # 准备传递给模板的参数字典
            format_args = {
                "title": item_title,
                "authors": ", ".join(item.get("authors", [])),
                "summary": item.get("summary", "N/A"),
                "url": item_url,
                "tldr": item.get('AI', {}).get('tldr', 'N/A'),
                "motivation": item.get('AI', {}).get('motivation', 'N/A'),
                "method": item.get('AI', {}).get('method', 'N/A'),
                "result": item.get('AI', {}).get('result', 'N/A'),
                "conclusion": item.get('AI', {}).get('conclusion', 'N/A'),
                "cate": item_main_category_list[0] if item_main_category_list else "N/A",
                "idx": current_item_idx,
                "assistant_link_markdown": assistant_link_markdown # 新增的参数
            }

            try:
                formatted_item_str = template_content.format(**format_args)
                formatted_items_for_category.append(formatted_item_str)
            except KeyError as e:
                print(f"警告: 模板文件 'paper_template.md' 中的占位符 {e} 未在数据中找到，条目 '{item_title}' 可能未正确格式化。")
            except Exception as e:
                print(f"警告: 格式化条目 '{item_title}' 时发生错误: {e}")


        markdown += "\n\n".join(formatted_items_for_category)

    # 写入Markdown文件
    # (保持原始的文件名逻辑，但可以考虑更稳健的路径处理)
    output_filename_base = args.data.split('_')[0]
    # 如果输入是 'mypapers.jsonl'，split('_')[0] 仍然是 'mypapers.jsonl'
    # 需要移除 .jsonl 后再处理下划线，或者确保输入符合 'name_date.jsonl' 格式
    if output_filename_base.endswith(".jsonl"):
        output_filename_base = output_filename_base[:-len(".jsonl")] # 移除 .jsonl
        # 如果原始文件名是 data.jsonl (没有下划线), 此时 output_filename_base 是 data
        # 如果原始文件名是 my_data.jsonl, 此时 output_filename_base 是 my_data, 再split('_')[0] 变成 my
        parts = output_filename_base.split('_')
        output_filename_base = parts[0]


    output_filename = output_filename_base + '.md'

    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"Markdown文件已生成: {output_filename}")
    except IOError as e:
        print(f"错误: 写入Markdown文件 {output_filename} 失败: {e}")

    print("\n重要提示:")
    print("1. 请确保您的 'paper_template.md' 文件已更新，包含了 '{assistant_link_markdown}' 占位符。")
    print("2. Kimi链接中的paper_id是根据论文URL（假定为arXiv格式）的最后一部分提取的。如果URL格式不同，可能需要调整提取逻辑。")
