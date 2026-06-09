import html
import re
from collections.abc import Callable
from html.parser import HTMLParser


class HtmlTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None
        self.in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.current_row = []
        if tag in {"td", "th"} and self.current_row is not None:
            self.current_cell = []
            self.in_cell = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.current_row is not None and self.current_cell is not None:
            self.current_row.append(normalize_whitespace("".join(self.current_cell)))
            self.current_cell = None
            self.in_cell = False
        if tag == "tr" and self.current_row is not None:
            if any(cell.strip() for cell in self.current_row):
                self.rows.append(self.current_row)
            self.current_row = None

    def handle_data(self, data: str) -> None:
        if self.in_cell and self.current_cell is not None:
            self.current_cell.append(data)


LATEX_REPLACEMENTS = {
    r"\times": "×",
    r"\cdot": "·",
    r"\div": "÷",
    r"\leq": "≤",
    r"\le": "≤",
    r"\geq": "≥",
    r"\ge": "≥",
    r"\neq": "≠",
    r"\ne": "≠",
    r"\approx": "≈",
    r"\sim": "≈",
    r"\pm": "±",
    r"\rightarrow": "→",
    r"\to": "→",
    r"\leftarrow": "←",
    r"\infty": "∞",
    r"\sum": "Σ",
    r"\prod": "Π",
    r"\int": "∫",
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\theta": "θ",
    r"\lambda": "λ",
    r"\mu": "μ",
    r"\pi": "π",
    r"\sigma": "σ",
    r"\omega": "ω",
}


def normalize_special_elements(content: str) -> str:
    normalized = html.unescape(content)
    normalized = convert_html_tables_to_markdown(normalized)
    normalized = convert_html_to_text(normalized)
    normalized = convert_latex_to_readable_text(normalized)
    return normalize_excess_blank_lines(normalized)


def convert_html_tables_to_markdown(content: str) -> str:
    def replace_table(match: re.Match[str]) -> str:
        parser = HtmlTableParser()
        parser.feed(match.group(0))
        return build_markdown_table(parser.rows)

    return re.sub(r"(?is)<table\b.*?</table>", replace_table, content)


def build_markdown_table(rows: list[list[str]]) -> str:
    normalized_rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not normalized_rows:
        return ""
    column_count = max(len(row) for row in normalized_rows)
    padded_rows = [row + [""] * (column_count - len(row)) for row in normalized_rows]
    header = padded_rows[0]
    separator = ["---"] * column_count
    body = padded_rows[1:]
    lines = [format_markdown_row(header), format_markdown_row(separator)]
    lines.extend(format_markdown_row(row) for row in body)
    return "\n".join(lines)


def format_markdown_row(row: list[str]) -> str:
    cells = [cell.replace("|", "/").strip() for cell in row]
    return "| " + " | ".join(cells) + " |"


def convert_html_to_text(content: str) -> str:
    normalized = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", content)
    normalized = re.sub(r"(?i)</\s*(p|div|section|article|tr|h[1-6])\s*>", "\n", normalized)
    normalized = re.sub(r"(?i)</\s*(td|th)\s*>\s*<\s*(td|th)\b[^>]*>", " | ", normalized)
    normalized = re.sub(r"(?i)<\s*li\b[^>]*>", "- ", normalized)
    normalized = re.sub(r"(?is)<script\b.*?</script>", "", normalized)
    normalized = re.sub(r"(?is)<style\b.*?</style>", "", normalized)
    normalized = re.sub(r"(?s)<[^>]+>", "", normalized)
    return html.unescape(normalized)


def convert_latex_to_readable_text(content: str) -> str:
    normalized = content
    normalized = re.sub(
        r"\\\[(.*?)\\\]",
        lambda match: convert_latex_expression(match.group(1)),
        normalized,
        flags=re.DOTALL,
    )
    normalized = re.sub(
        r"\\\((.*?)\\\)",
        lambda match: convert_latex_expression(match.group(1)),
        normalized,
        flags=re.DOTALL,
    )
    normalized = re.sub(
        r"\$\$(.*?)\$\$",
        lambda match: convert_latex_expression(match.group(1)),
        normalized,
        flags=re.DOTALL,
    )
    normalized = re.sub(
        r"(?<!\$)\$([^$\n]+)\$(?!\$)",
        lambda match: convert_latex_expression(match.group(1)),
        normalized,
    )
    normalized = convert_latex_expression(normalized)
    return normalized


def convert_latex_expression(expression: str) -> str:
    readable = expression
    readable = re.sub(r"\\begin\{[^}]+\}|\\end\{[^}]+\}", "", readable)
    readable = readable.replace("\\\\", "\n").replace("&", " ")
    readable = replace_latex_group_command(
        readable,
        "frac",
        lambda values: f"({values[0]})/({values[1]})" if len(values) == 2 else values[0],
    )
    readable = replace_latex_group_command(readable, "sqrt", lambda values: f"√({values[0]})")
    readable = replace_latex_group_command(readable, "text", lambda values: values[0])
    readable = replace_latex_group_command(readable, "mathrm", lambda values: values[0])
    readable = replace_latex_group_command(readable, "mathbf", lambda values: values[0])
    readable = replace_latex_group_command(readable, "operatorname", lambda values: values[0])
    for source, replacement in LATEX_REPLACEMENTS.items():
        readable = readable.replace(source, replacement)
    readable = re.sub(r"\^\{([^}]+)\}", r"^\1", readable)
    readable = re.sub(r"_\{([^}]+)\}", r"_\1", readable)
    readable = re.sub(r"\\[a-zA-Z]+", "", readable)
    readable = readable.replace("{", "").replace("}", "")
    return normalize_whitespace(readable)


def replace_latex_group_command(
    content: str,
    command: str,
    formatter: Callable[[list[str]], str],
) -> str:
    pattern = re.compile(rf"\\{command}\{{([^{{}}]*)\}}(?:\{{([^{{}}]*)\}})?")

    def replace(match: re.Match[str]) -> str:
        values = [value for value in match.groups() if value is not None]
        return formatter(values)

    previous = None
    current = content
    while previous != current:
        previous = current
        current = pattern.sub(replace, current)
    return current


def normalize_whitespace(content: str) -> str:
    return re.sub(r"[ \t]+", " ", content).strip()


def normalize_excess_blank_lines(content: str) -> str:
    lines = [line.rstrip() for line in content.splitlines()]
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()
