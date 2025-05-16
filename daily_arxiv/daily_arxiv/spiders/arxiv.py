import scrapy
import os
import re
import logging # 用于日志记录

class ArxivSpider(scrapy.Spider):
    name = "arxiv"  # 爬虫名称
    allowed_domains = ["arxiv.org"]  # 允许爬取的域名

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # --- START: 基本保持用户原始 __init__ 逻辑 ---
        categories_env_str = os.environ.get("CATEGORIES", "cs.CV")
        categories_list = categories_env_str.split(",")
        # categories 变量现在是处理后的列表，例如 ['cs.CV', 'cs.LG']
        categories = list(map(str.strip, categories_list))
        
        self.start_urls = [
            f"https://arxiv.org/list/{cat}/new" for cat in categories
        ]  # 起始URL（计算机科学领域的最新论文）
        # --- END: 基本保持用户原始 __init__ 逻辑 ---

        # 将处理后的类别列表存储为成员变量，以便在 parse 方法中使用进行过滤
        self.filter_categories = categories 
        
        self.logger.info(f"爬虫已初始化。目标类别 (用于过滤): {self.filter_categories}")
        self.logger.info(f"起始 URLs: {self.start_urls}")

    def parse(self, response):
        self.logger.info(f"正在解析 URL: {response.url}")

        anchors = []
        for li in response.css("div[id=dlpage] ul li"):
            href_val = li.css("a::attr(href)").get()
            if href_val and "item" in href_val:
                try:
                    anchor_num_str = href_val.split("item")[-1]
                    anchor_num_str = re.split(r'[,&]', anchor_num_str)[0] # 进一步清理
                    anchors.append(int(anchor_num_str))
                except ValueError:
                    self.logger.warning(f"无法从 href 解析锚点数字: {href_val}")
                except IndexError:
                    self.logger.warning(f"从 href 解析锚点时发生索引错误: {href_val}")
        
        if not anchors:
            self.logger.debug(f"在页面 {response.url} 未找到有效锚点。")

        papers_dt_list = response.css("dl dt")
        if not papers_dt_list:
            self.logger.info(f"在 {response.url} 上未找到论文 (dl dt 为空)。")
            return

        for paper_dt in papers_dt_list: # paper_dt 对应原始代码中的 paper 变量（在循环中）
            if anchors:
                try:
                    item_name_attr = paper_dt.css("a[name^='item']::attr(name)").get()
                    if item_name_attr and "item" in item_name_attr:
                        item_number = int(item_name_attr.split("item")[-1])
                        if item_number >= anchors[-1]:
                            continue
                    else:
                        self.logger.warning(f"无法找到论文的 item name 属性: {paper_dt.get()}")
                except (ValueError, IndexError) as e:
                    self.logger.error(f"处理论文锚点逻辑时出错: {paper_dt.get()}: {e}")
                    continue

            # 提取论文ID链接，为 yield 和日志做准备
            paper_id_href = paper_dt.css("a[title='Abstract']::attr(href)").get()
            if not paper_id_href: # 如果无法提取ID链接，则跳过此论文
                self.logger.warning(f"无法从 dt 提取论文ID链接，跳过此条目: {paper_dt.get()}")
                continue
            
            # 从链接中解析出论文ID (例如 '2301.00001')
            current_paper_id = paper_id_href.split("/")[-1]

            dd_element = paper_dt.xpath("following-sibling::dd[1]")
            if not dd_element:
                self.logger.warning(f"未找到论文 {current_paper_id} 的 dd 元素。跳过。")
                continue

            primary_category_code = None
            primary_subject_span_text = dd_element.css("div.list-subjects span.primary-subject ::text").get()
            if primary_subject_span_text:
                primary_category_code = primary_subject_span_text.strip()
            else:
                subjects_div_text_all = "".join(dd_element.css("div.list-subjects ::text").getall()).strip()
                if subjects_div_text_all.startswith("Subjects:"):
                    subjects_content = subjects_div_text_all[len("Subjects:"):].strip()
                else:
                    subjects_content = subjects_div_text_all

                if subjects_content:
                    first_subject_full_text = subjects_content.split(';')[0].strip()
                    if first_subject_full_text:
                        match = re.search(r'\(([^)]+)\)$', first_subject_full_text)
                        if match:
                            code_in_parens = match.group(1).strip()
                            if '.' in code_in_parens or re.fullmatch(r"[a-z0-9\-]+(?:\.[A-Z0-9\-]+)*", code_in_parens, re.IGNORECASE):
                                primary_category_code = code_in_parens
                            else:
                                primary_category_code = code_in_parens 
                                self.logger.debug(f"论文 {current_paper_id}: 从 '{first_subject_full_text}' 的括号中提取了类别 '{primary_category_code}'，但其格式校验较弱。")
                        else:
                            primary_category_code = first_subject_full_text
                            if not ('.' in primary_category_code or re.fullmatch(r"[a-z0-9\-]+(?:\.[A-Z0-9\-]+)*", primary_category_code, re.IGNORECASE)):
                                self.logger.warning(f"论文 {current_paper_id}: 解析得到的首要类别 '{primary_category_code}' (来自 '{first_subject_full_text}', 无括号) 格式校验较弱。")
            
            if not primary_category_code:
                self.logger.warning(f"论文 {current_paper_id}: 未能确定其主要类别。跳过。")
                continue

            if primary_category_code not in self.filter_categories:
                self.logger.info(f"跳过论文 {current_paper_id} (主要类别: {primary_category_code})，因为它不在目标类别列表 {self.filter_categories} 中。")
                continue
            
            self.logger.debug(f"正在处理论文 {current_paper_id} (主要类别: {primary_category_code})")
            # yield 的输出与原始代码保持一致
            yield {
                "id": current_paper_id, # 使用从链接中提取的 paper_id
            }
