from types import SimpleNamespace

import pytest

from javlib.sources import fetch_jav321, parse_jav321


def detail(page_id, plot="Example synopsis."):
    # Match the site's metadata panel and direct-text synopsis layout.
    return (
        '<div class="panel-body"><div class="row"><div class="col-md-9">'
        f'<b>品番:</b> {page_id}<br><b>メーカー:</b> Example'
        '</div></div><div class="row"><div class="col-md-12"></div></div>'
        f'<div class="row"><div class="col-md-12">{plot}'
        '<p>Advertisement</p><h2>Recommendations</h2>'
        '<a href="/video/other">Unrelated title</a><script>tracking()</script>'
        '</div></div></div>'
    )


@pytest.mark.parametrize(
    ("code", "page_id"),
    [("SONE-035", "sone-035"), ("SONE-035", "SONE_00035"),
     ("300MIUM-865", "300mium00865")],
)
def test_plot_requires_matching_complete_id_and_excludes_nested_text(code, page_id):
    data = parse_jav321(detail(page_id, "あらすじ &amp; &lt;説明&gt;<br>続き。"), code)

    assert data == {
        "source": "jav321", "code": code, "dvdid": page_id,
        "plot": "あらすじ & <説明> 続き。",
    }


@pytest.mark.parametrize(
    ("code", "page_id"),
    [
        ("SONE-035", "SONE-036"), ("SONE-035", ""),
        ("999MIUM-865", "MIUM-865"), ("999MIUM-865", "300MIUM-865"),
        ("300MIUM-865", "MIUM-865"), ("13DSVR-1968", "DSVR-1968"),
        ("723GGH-009", "GGH-009"),
    ],
)
def test_missing_mismatched_or_shortened_id_is_rejected(code, page_id):
    page = f"<title>{code}</title>" + detail(page_id)
    assert parse_jav321(page, code) is None


@pytest.mark.parametrize(
    "page",
    [
        '<input name="sn" value="SONE-035">',
        detail("sone-035").replace("品番:", "タイトル:"),
        detail("sone-035", " \n &nbsp; "),
        detail("sone-035", "<p>Only nested content</p>"),
        detail("sone-035", "") + detail("sone-036"),
        detail("sone-036") + detail("sone-035"),
        detail("sone-035").replace(
            "<b>メーカー:</b>", "<b>品番:</b> sone-036<br><b>メーカー:</b>"
        ),
        detail("sone-035").replace(
            '</div></div></div>',
            '</div></div><div class="row"><div class="col-md-12">'
            'Ambiguous second block</div></div></div>',
        ),
    ],
)
def test_missing_or_ambiguous_metadata_cannot_supply_a_plot(page):
    assert parse_jav321(page, "SONE-035") is None


def test_plot_from_a_different_panel_is_not_attached_to_the_id():
    page = detail("sone-035", "") + detail("sone-036").replace("品番:", "タイトル:")
    assert parse_jav321(page, "SONE-035") is None


def test_search_posts_code_once_and_parses_returned_detail(controlled_fetcher):
    response = SimpleNamespace(status_code=200, headers={}, text=detail("sone-035"))
    fetcher, _, _ = controlled_fetcher([response])

    assert fetch_jav321(fetcher, "SONE-035")["plot"] == "Example synopsis."
    assert fetcher.s.requests == [
        ("POST", "https://www.jav321.com/search",
         {"Referer": "https://www.jav321.com/"}, {"sn": "SONE-035"}, 30)
    ]
