from services.pdf_service import _parse_extract_response


def test_parse_extract_response_strips_markdown_json_fence():
    response = _parse_extract_response(
        """```json
{
  "materials": [
    {
      "title": "Portfolio backend",
      "summary": "Built API integration.",
      "material_type": "PROJECT"
    }
  ]
}
```"""
    )

    assert len(response.materials) == 1
    assert response.materials[0].title == "Portfolio backend"
    assert response.materials[0].material_type == "PROJECT"


def test_parse_extract_response_recovers_bare_materials_payload():
    response = _parse_extract_response(
        '''```json
"materials": [
  {
    "title": "Notion import",
    "summary": null,
    "material_type": "EXPERIENCE"
  }
]
```'''
    )

    assert len(response.materials) == 1
    assert response.materials[0].title == "Notion import"
    assert response.materials[0].summary is None


def test_parse_extract_response_extracts_json_object_from_surrounding_text():
    response = _parse_extract_response(
        'Here is the JSON: {"materials": []}'
    )

    assert response.materials == []
