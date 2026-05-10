"""PDF extractor placeholders."""

from __future__ import annotations

from dorje.handles import HandleStore
from dorje_sdk import tool
from extractors_common import get_file_ref


@tool(description="Placeholder PDF-to-Markdown extractor. Requires a future PDF backend before it can emit derivatives.", produces="extracted_markdown")
def extract_pdf_to_markdown(handle: str, label: str = "") -> dict[str, object]:
    del label
    record = get_file_ref(HandleStore(), handle)
    if record.content_type != "application/pdf":
        raise ValueError("extract_pdf_to_markdown requires an application/pdf file_ref handle")
    raise NotImplementedError("PDF-to-Markdown extraction backend is not installed yet")


@tool(description="Placeholder PDF image extractor. Requires a future PDF image backend before it can emit derivatives.", produces="collection/image")
def extract_images_from_pdf(handle: str, label: str = "") -> dict[str, object]:
    del label
    record = get_file_ref(HandleStore(), handle)
    if record.content_type != "application/pdf":
        raise ValueError("extract_images_from_pdf requires an application/pdf file_ref handle")
    raise NotImplementedError("PDF image extraction backend is not installed yet")


@tool(description="Placeholder PDF figure extractor. Requires a future PDF figure backend before it can emit derivatives.", produces="collection/figure")
def extract_figures_from_pdf(handle: str, label: str = "") -> dict[str, object]:
    del label
    record = get_file_ref(HandleStore(), handle)
    if record.content_type != "application/pdf":
        raise ValueError("extract_figures_from_pdf requires an application/pdf file_ref handle")
    raise NotImplementedError("PDF figure extraction backend is not installed yet")


@tool(description="Placeholder PDF table extractor. Requires a future PDF table backend before it can emit derivatives.", produces="collection/table")
def extract_tables_from_pdf(handle: str, label: str = "") -> dict[str, object]:
    del label
    record = get_file_ref(HandleStore(), handle)
    if record.content_type != "application/pdf":
        raise ValueError("extract_tables_from_pdf requires an application/pdf file_ref handle")
    raise NotImplementedError("PDF table extraction backend is not installed yet")
