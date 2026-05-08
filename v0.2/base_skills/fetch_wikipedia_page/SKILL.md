# Fetch Wikipedia Page

Use this skill when the user asks to fetch, retrieve, download, or get a Wikipedia page, but does not explicitly ask for summarization, indexing, chunking, or analysis.

## Process

1. Identify the Wikipedia page title from the user's request.
2. Call `get_from_wikipedia` with that title.
3. Do not call `read_handle`, `chunk_md_handle`, or summarization tools unless the user explicitly asks for them.
4. Return the handle metadata from `get_from_wikipedia` in a concise Markdown response.

## Output

Return Markdown with this shape:

```md
# Wikipedia Page Fetched

- Title: <title/label>
- Handle: `<handle>`
- Content type: `<content_type>`
- SHA-256: `<sha256>`
- Size: <char_count> characters

Preview:
<short preview from the tool result>
```
