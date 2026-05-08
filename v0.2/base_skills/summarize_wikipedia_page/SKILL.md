# Summarize Wikipedia Page

Use this skill when the user wants a concise summary of a Wikipedia page or Wikipedia-derived Markdown.

## Process

1. If the page content is not already provided, use the `get_from_wikipedia` tool with the user's requested page title.
2. `get_from_wikipedia` returns a Markdown content handle, not the full page text.
3. Use `read_handle` to read the handle when you need page content.
4. If the page is long, use `chunk_md_handle` before detailed analysis.
5. Produce a grounded Markdown summary.
6. Do not invent facts that are not present in the source text.
7. Prefer plain language over dense encyclopedic prose.

## Output

Return Markdown with this shape:

```md
# <Page Title> — Summary

## Short summary
<3-5 sentences>

## Key points
- <important fact>
- <important fact>
- <important fact>

## Why it matters
<1 short paragraph>
```

If the source text is too thin or ambiguous, say so briefly.
