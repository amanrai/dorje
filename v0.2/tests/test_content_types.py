from dorje.content_types import guess_content_type, is_code_media_type


def test_guess_content_type_uses_stable_code_types() -> None:
    assert guess_content_type("a.py") == "text/x-code-python"
    assert guess_content_type("A.java") == "text/x-code-java"
    assert guess_content_type("x.c") == "text/x-code-c"
    assert guess_content_type("x.cpp") == "text/x-code-cpp"
    assert guess_content_type("x.rs") == "text/x-code-rust"
    assert guess_content_type("app.js") == "text/x-code-javascript"
    assert guess_content_type("app.jsx") == "text/x-code-jsx"
    assert guess_content_type("app.ts") == "text/x-code-typescript"
    assert guess_content_type("app.tsx") == "text/x-code-tsx"
    assert guess_content_type("style.css") == "text/x-code-css"
    assert guess_content_type("style.scss") == "text/x-code-scss"
    assert guess_content_type("style.sass") == "text/x-code-sass"
    assert guess_content_type("style.less") == "text/x-code-less"
    assert guess_content_type("Component.vue") == "text/x-code-vue"
    assert guess_content_type("Component.svelte") == "text/x-code-svelte"
    assert guess_content_type("Page.astro") == "text/x-code-astro"
    assert is_code_media_type(guess_content_type("a.py"))


def test_guess_content_type_overrides_common_text_types() -> None:
    assert guess_content_type("README.md") == "text/markdown"
    assert guess_content_type("data.jsonl") == "application/x-ndjson"
    assert guess_content_type("page.xhtml") == "application/xhtml+xml"
