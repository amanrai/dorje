# Summarize Wikipedia Page

Use this skill when the user wants a concise summary of a Wikipedia page or Wikipedia-derived Markdown.

## Process

1. If the page content is not already provided, use the `get_from_wikipedia` tool with the user's requested page title.
2. Read the returned Markdown as source text.
3. Produce a grounded Markdown summary.
4. Do not invent facts that are not present in the source text.
5. Prefer plain language over dense encyclopedic prose.

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
