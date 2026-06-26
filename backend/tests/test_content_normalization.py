from app.services.content_normalization import normalize_special_elements


def test_normalize_special_elements_converts_html_table_to_markdown_table() -> None:
    content = (
        "<table><tr><th>指标</th><th>数值</th></tr>"
        "<tr><td>覆盖率</td><td>95%</td></tr></table>"
    )

    normalized = normalize_special_elements(content)

    assert normalized == "| 指标 | 数值 |\n| --- | --- |\n| 覆盖率 | 95% |"


def test_normalize_special_elements_converts_latex_to_readable_text() -> None:
    content = r"公式为 \( y = \frac{a}{b} \times \sqrt{x} \leq 10 \)。"

    normalized = normalize_special_elements(content)

    assert normalized == "公式为 y = (a)/(b) × √(x) ≤ 10。"


def test_normalize_special_elements_strips_regular_html_tags() -> None:
    content = "<p>第一行<br/>第二行</p><div>第三行</div>"

    normalized = normalize_special_elements(content)

    assert normalized == "第一行\n第二行\n第三行"
