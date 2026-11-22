from cityuschedule.ge_importer import parse_ge_html


def test_parses_current_cityu_ge_course_list_layout(tmp_path):
    html = tmp_path / "page2.html"
    html.write_text(
        """
        <table class="ax-mobile-table">
          <tbody>
            <tr>
              <td><a href="/ge_info/Course/GE2108">
                GE2108 - Literature in our Lives
              </a></td>
              <td><span>Area 1</span></td>
              <td>EN</td>
              <td>B2, A2</td>
              <td>
                <div class="label-icon A">2026-27 Sem A</div>
                <div class="label-icon B">2026-27 Sem B</div>
              </td>
              <td><span>Yes</span></td>
            </tr>
          </tbody>
        </table>
        """,
        encoding="utf-8",
    )

    assert parse_ge_html(html) == [
        {
            "course_code": "GE2108",
            "course_title": "Literature in our Lives",
            "area": "Area 1",
            "category": "Area 1",
            "offering_unit": "EN",
            "level": "B2, A2",
            "terms": ["2026-27 Sem A", "2026-27 Sem B"],
            "with_exam": True,
            "cross_institutional": False,
            "partner_institutions": [],
        }
    ]
