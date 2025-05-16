import scrapy
import os
import re
import logging # 用于日志记录

class ArxivSpider(scrapy.Spider):
    name = "arxiv"  # 爬虫名称
    allowed_domains = ["arxiv.org"]  # 允许爬取的域名

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categories_env_str = os.environ.get("CATEGORIES", "cs.CV")
        categories_list = categories_env_str.split(",")
        categories = list(map(str.strip, categories_list))
        
        self.start_urls = [
            f"https://arxiv.org/list/{cat}/new" for cat in categories
        ]
        self.filter_categories = categories 
        
        self.logger.info(f"爬虫已初始化。目标类别 (用于过滤): {self.filter_categories}")
        self.logger.info(f"起始 URLs: {self.start_urls}")

    def _extract_arxiv_category_code(self, raw_text, paper_id_for_log, logger_instance):
        """
        从包含类别描述的原始文本中提取纯粹的 arXiv 类别代码。
        例如从 "Computation and Language (cs.CL)" 提取 "cs.CL"。
        """
        if not raw_text:
            return None
        
        stripped_text = raw_text.strip()
        final_code_candidate = None

        # 优先规则 1: 尝试从末尾的括号中提取代码，例如 "Description (CODE)"
        match_paren = re.search(r'\(([^)]+)\)$', stripped_text)
        if match_paren:
            candidate_in_paren = match_paren.group(1).strip()
            # 校验括号内的内容是否像一个 arXiv 代码
            if '.' in candidate_in_paren or re.fullmatch(r"[a-z0-9\-]+(?:\.[A-Z0-9\-]+)*", candidate_in_paren, re.IGNORECASE):
                final_code_candidate = candidate_in_paren
                logger_instance.debug(f"论文 {paper_id_for_log}: 从 '{raw_text}' 的括号中提取代码 '{final_code_candidate}'")
            else:
                logger_instance.debug(f"论文 {paper_id_for_log}: '{raw_text}' 的括号中内容 '{candidate_in_paren}' 未被识别为有效代码格式。")

        # 优先规则 2: 如果规则1未成功，尝试从括号前部分或整个字符串提取代码
        # 这适用于 "CODE (Description)" 或单独的 "CODE"
        if not final_code_candidate:
            # 取第一个 '(' 前的部分，如果没有 '(', 则取整个字符串
            candidate_before_paren = stripped_text.split('(', 1)[0].strip()
            if candidate_before_paren: # 确保不为空
                # 校验这部分是否像一个 arXiv 代码
                if '.' in candidate_before_paren or re.fullmatch(r"[a-z0-9\-]+(?:\.[A-Z0-9\-]+)*", candidate_before_paren, re.IGNORECASE):
                    # 额外检查：如果包含空格但又没有 '.' 或 '-' (例如 "Computation and Language")，则可能不是代码
                    if ' ' in candidate_before_paren and not ('.' in candidate_before_paren or '-' in candidate_before_paren):
                        logger_instance.debug(f"论文 {paper_id_for_log}: 候选代码 '{candidate_before_paren}' (来自 '{raw_text}') 包含空格且无点/中划线，判定为无效代码。")
                    else:
                        final_code_candidate = candidate_before_paren
                        logger_instance.debug(f"论文 {paper_id_for_log}: 从 '{raw_text}' 的括号前部分或整个字符串提取代码 '{final_code_candidate}'")
                else:
                    logger_instance.debug(f"论文 {paper_id_for_log}: '{raw_text}' 的括号前部分或整个字符串 '{candidate_before_paren}' 未被识别为有效代码格式。")
            else: # 例如，原始文本是 " (cs.CL) "，括号前部分为空
                 logger_instance.debug(f"论文 {paper_id_for_log}: 文本 '{raw_text}' 的括号前部分为空或仅含空格。")


        if not final_code_candidate:
            logger_instance.warning(f"论文 {paper_id_for_log}: 无法从原始文本 '{raw_text}' 中明确提取类别代码。")
        
        return final_code_candidate

    def parse(self, response):
        self.logger.info(f"正在解析 URL: {response.url}")

        anchors = []
        for li in response.css("div[id=dlpage] ul li"):
            href_val = li.css("a::attr(href)").get()
            if href_val and "item" in href_val:
                try:
                    anchor_num_str = href_val.split("item")[-1]
                    anchor_num_str = re.split(r'[,&]', anchor_num_str)[0]
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

        for paper_dt in papers_dt_list:
            if anchors:
                try:
                    item_name_attr = paper_dt.css("a[name^='item']::attr(name)").get()
                    if item_name_attr and "item" in item_name_attr:
                        item_number = int(item_name_attr.split("item")[-1])
                        if item_number >= anchors[-1]:
                            continue
                    # else: # 原始代码中没有针对 item_name_attr 未找到的日志，保持一致
                    #    self.logger.warning(f"无法找到论文的 item name 属性: {paper_dt.get()}")
                except (ValueError, IndexError) as e:
                    self.logger.error(f"处理论文锚点逻辑时出错: {paper_dt.get()}: {e}")
                    continue

            paper_id_href = paper_dt.css("a[title='Abstract']::attr(href)").get()
            if not paper_id_href:
                self.logger.warning(f"无法从 dt 提取论文ID链接，跳过此条目: {paper_dt.get()}")
                continue
            current_paper_id = paper_id_href.split("/")[-1]

            dd_element = paper_dt.xpath("following-sibling::dd[1]")
            if not dd_element:
                self.logger.warning(f"未找到论文 {current_paper_id} 的 dd 元素。跳过。")
                continue

            # --- 开始提取和处理主要类别代码 ---
            raw_subject_text_to_parse = None # 将用于提取纯代码的原始文本
            
            # 尝试从 span.primary-subject 获取
            primary_subject_span_text = dd_element.css("div.list-subjects span.primary-subject ::text").get()
            if primary_subject_span_text:
                raw_subject_text_to_parse = primary_subject_span_text # 不需要 strip() 在这里，辅助函数会处理
                self.logger.debug(f"论文 {current_paper_id}: 从 span.primary-subject 获取到原始文本: '{raw_subject_text_to_parse}'")
            else:
                # 如果 span 未找到, 则解析 div.list-subjects 的整体文本
                self.logger.debug(f"论文 {current_paper_id}: 未找到 span.primary-subject，尝试解析 div.list-subjects。")
                subjects_div_text_all = "".join(dd_element.css("div.list-subjects ::text").getall()).strip()
                
                if subjects_div_text_all.startswith("Subjects:"):
                    subjects_content = subjects_div_text_all[len("Subjects:"):].strip()
                else:
                    subjects_content = subjects_div_text_all

                if subjects_content:
                    first_subject_full_text = subjects_content.split(';')[0].strip() # 取第一个分号前的部分
                    if first_subject_full_text:
                        raw_subject_text_to_parse = first_subject_full_text
                        self.logger.debug(f"论文 {current_paper_id}: 从 div.list-subjects 解析到首个学科条目: '{raw_subject_text_to_parse}'")
                    else:
                        self.logger.warning(f"论文 {current_paper_id}: 从 div.list-subjects 解析到的首个学科条目为空。")
                else:
                    self.logger.warning(f"论文 {current_paper_id}: div.list-subjects 内容为空或无法解析。")

            primary_category_code = None
            if raw_subject_text_to_parse:
                primary_category_code = self._extract_arxiv_category_code(raw_subject_text_to_parse, current_paper_id, self.logger)
            # --- 提取和处理主要类别代码结束 ---
            
            if not primary_category_code: # 如果未能提取出代码
                self.logger.warning(f"论文 {current_paper_id}: 未能从原始学科文本 '{raw_subject_text_to_parse if raw_subject_text_to_parse else 'N/A'}' 中确定其主要类别代码。跳过。")
                continue

            # 核心过滤逻辑
            if primary_category_code not in self.filter_categories:
                # 现在日志中的 primary_category_code 应该是纯代码了
                self.logger.info(f"跳过论文 {current_paper_id} (主要类别: {primary_category_code})，因为它不在目标类别列表 {self.filter_categories} 中。")
                continue
            
            self.logger.debug(f"正在处理论文 {current_paper_id} (主要类别: {primary_category_code})")
            yield {
                "id": current_paper_id,
            }
