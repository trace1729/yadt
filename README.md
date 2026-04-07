# YAET: Yet Another epub Translator

将 EPUB 或 Markdown 书稿转换成中英对照 Markdown，并可重新导出为 EPUB。

仓库当前提供的是一组小而清晰的脚本：

- `src/run_book_pipeline.py`: 一键执行 `epub -> markdown -> heading fix -> translate -> cleanup -> epub`
- `src/convert_epub_to_markdown.py`: 将 EPUB 转成 Markdown，并导出图片资源
- `src/translate_markdown_book.py`: 将 Markdown 翻译成中英对照或纯中文 Markdown
- `src/cleanup_bilingual_markdown.py`: 合并双语标题、更新目录链接、去除重复图片和分隔符
- `src/fix_special_toc_links.py`: 修复特殊目录链接 edge case，例如 `STATE CHANGE -> #STATE_CHANGE`
- `src/convert_markdown_to_epub.py`: 将 Markdown 转回 EPUB，并保留粗体、斜体和封面
- `src/monitor_translation_progress.py`: 查看翻译缓存进度
- `src/translate_text_cli.py`: 单句或短文本翻译 CLI
- `src/output_paths.py`: 统一输出路径规则

## Install

```bash
python3 -m pip install -r requirements.txt
```

在项目根目录提供 API key：

```bash
echo 'DEEPSEEK_API_KEY="your_api_key"' > .env
```

也可以直接导出环境变量：

```bash
export DEEPSEEK_API_KEY="your_api_key"
```

## Quick Start

完整处理一本 EPUB：

```bash
./.venv/bin/python src/run_book_pipeline.py "/path/to/book.epub" --max-workers 16
```

默认输出会放到：

```text
output/<Book_Name_With_Underscores>/
```

例如：

```text
output/The_Paper_Menagerie_and_Oth_(Z-Library)/
```

其中通常会包含：

- `<book>.md`
- `<book>.translation_cache.json`
- `<book>.bilingual.md`
- `<book>.bilingual.epub`
- `<book>_assets/`

## Step By Step

### 1. EPUB -> Markdown

```bash
./.venv/bin/python src/convert_epub_to_markdown.py "/path/to/book.epub"
```

默认行为：

- 按阅读顺序导出为单个 Markdown
- 自动生成目录
- 保留章节层级
- 导出图片到同目录下的 `<book>_assets/`
- 自动检测封面图片，包括 `titlepage.xhtml` 中 SVG 引用的 `cover.jpeg`

### 2. Fix Special TOC Links

有些 EPUB 的目录项不是标准 Markdown anchor，而是类似：

```text
[STATE CHANGE](index_split_007.html#filepos28997)
```

这类文件可以用：

```bash
./.venv/bin/python src/fix_special_toc_links.py output/<book>/<book>.md
```

当前规则比较保守，只会对全大写且不过长的特殊标题生效，尽量避免误伤正常标题。

### 3. Translate Markdown

```bash
./.venv/bin/python src/translate_markdown_book.py output/<book>/<book>.md --max-workers 16
```

默认会生成：

```text
output/<book>/<book>.bilingual.md
output/<book>/<book>.translation_cache.json
```

纯中文输出：

```bash
./.venv/bin/python src/translate_markdown_book.py output/<book>/<book>.md --output-mode chinese
```

可选参数：

- `--model`: 默认 `deepseek-chat`
- `--max-chars-per-chunk`: 默认 `6000`
- `--cache-path`: 指定缓存路径
- `--max-workers`: 批次级并发数
- `--no-resume`: 不使用缓存续跑

### 4. Cleanup Bilingual Markdown

```bash
./.venv/bin/python src/cleanup_bilingual_markdown.py output/<book>/<book>.bilingual.md
```

当前后处理会：

- 合并中英文相邻标题
- 更新目录和引用链接文字
- 去掉重复图片
- 去掉 `∞∞∞∞...` 这类分隔符

### 5. Markdown -> EPUB

```bash
./.venv/bin/python src/convert_markdown_to_epub.py output/<book>/<book>.bilingual.md
```

默认会：

- 按 Markdown 标题切分章节
- 生成 EPUB TOC
- 保留 `*`, `**`, `***`, `_`, `__`, `___` 的内联强调格式
- 嵌入图片资源
- 将 `cover*` 图片优先设为 EPUB cover
- 如果没有 `cover*`，回退到第一张图片作为封面

## Progress Monitor

查看翻译进度：

```bash
./.venv/bin/python src/monitor_translation_progress.py output/<book>/<book>.md --cache-path output/<book>/<book>.translation_cache.json
```

支持：

- `--once`: 只打印一次
- `--width`: 调整进度条宽度

## Text Translation CLI

```bash
./.venv/bin/python src/translate_text_cli.py "Hello world"
./.venv/bin/python src/translate_text_cli.py --verbose "Hello world"
```

默认只输出译文。

`--verbose` 还会输出 pronunciation 和 example sentence。

## Naming Notes

默认输出目录和文件名都会做标准化：

- 书名中的空格会替换为下划线 `_`
- 连续空格或下划线会折叠成单个下划线
- 原始输入文件不会被自动重命名

## Recommended Workflow

对于普通 EPUB：

```bash
./.venv/bin/python src/run_book_pipeline.py "/path/to/book.epub" --max-workers 16
```

对于已知存在特殊目录链接的 EPUB：

`src/run_book_pipeline.py` 已经内置 `src/fix_special_toc_links.py` 这一步，一般不需要手工再跑。

## Repository Notes

- 术语表内置在 `src/translate_markdown_book.py` 的 `GLOSSARY` 中
- 图片缓存默认放在输出目录下的 `.epub_image_cache/`
- 翻译缓存是 JSON，可复用来续跑大书
- API 调用会产生费用，建议先试跑小样本
